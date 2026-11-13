# Google Colab CLI 安定運用・CCU節約スキル

[English](README.md) · [スキル本体](skills/colab-cli-reliable/SKILL.md) · [MITライセンス](LICENSE)

Google公式の **google-colab-cli** をAIエージェントから扱い、CPUでの準備、GPU／TPUでの計算、切断復旧、成果物回収、ランタイム解放までを一貫して運用するためのOSSスキルです。

目標は **「必要な品質・件数・期限を満たす成果物までの総CCUを最小化する」** ことです。このリポジトリでは、CUとCCUはいずれもColabのcompute unitsを指します。Google公式スキルではなく、公式CLIを使うための独立したコミュニティプロジェクトです。

- **作成日時：2026年11月13日 18:25:10 JST**（2026-11-13T09:25:10Z、初回保存時点）
- **情報確認日：2026年11月13日**
- 本体を短い12の規則にし、詳しい手順と変化しやすい情報を参照資料へ分離しています。
- 本調査・検証のためにColabランタイムを割り当てたり、CCUを消費したりしていません。

## CPUでアップロードしてから切り替える際の注意

**CPUで準備する方針は有効ですが、CPUの `/content` に置いたファイルはGPU／TPUへそのまま引き継がれません。** ランタイム種別変更は、元のVMを終了して新しいVMを作る処理です。[Colab開発者の説明](https://github.com/googlecolab/colab-vscode/discussions/265)

推奨する順序は次のとおりです。

1. 手元のCPUで入力検証・前処理・分割・設定確認を行う。必要な場合だけColab CPUを使う。
2. 入力、コード、依存関係の記録、ファイルのハッシュをDrive等の永続保存先へコピーする。
3. 保存先のサイズ・ハッシュを確認し、不要になったCPUランタイムを解放する。
4. 目的のGPU／TPUを新規確保し、実機・バックエンド・メモリ・デバイス数を確認する。
5. 必要なデータだけ復元し、小さな正解テストと代表処理の計測を経て本処理へ進む。
6. 結果を永続化・検証して解放し、グラフ作成などCPUだけで済む後処理を続ける。

手元からDriveへ直接アップロードできるなら、Colab CPUを挟まない方が簡単な場合があります。CPU／high-RAMの消費率をゼロと決めつけず、追加の転送・復元時間まで比較します。小さいデータでは、GPU確保後に直接転送する方が安い場合もあります。[CPU準備・保存・費用の詳細](skills/colab-cli-reliable/references/cost-and-staging.md)

## 最優先の節約原則

| 原則 | スキルに入れた判断 |
| --- | --- |
| 総量で比較する | 時間単価ではなく、準備・転送・コンパイル・評価・保存・待機を含める |
| 品質を守る | 精度不足、未処理、重複、評価データの欠落を高速化として数えない |
| 早く確保しすぎない | 入力準備や人の確認待ちでGPU／TPUを放置しない |
| 短く試す | 本番に近い小規模計測を行い、最適化そのものの費用にも上限を設ける |
| 律速を直す | I/O待ちやCPU前処理が原因なら、機種の大型化より先に改善する |
| 二重実行しない | 切断時は結果不明として、元のジョブの証拠を確認する |
| 解放まで確認する | 保存の完了と整合性を確かめ、所有しているendpointだけ解放する |

比較の基本式は `推定CU = Σ（各ランタイムのCU/時 × 割当秒数 / 3600）` です。同時に複数ランタイムを保持すれば両方を加算します。実際の料金表や会計上の保証ではなく、観測した消費率を使う計画・比較用の推定です。現在の `colab usage` はアカウント全体の表示なので、複数ジョブが動いている場合は個別費用の帰属に注意します。[公式CLI仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md)

## GPUを効率よく使う

- DataLoader、前処理、転送を計測し、デバイスへ入力を供給し続ける。
- 対応するmixed precisionを候補にし、NaN・損失・評価品質を確認する。
- バッチをメモリ上限まで無条件に増やさず、実効バッチや学習条件を維持する。
- 推論では適切な評価モードと不要な勾配計算の停止を使う。
- `.item()`、CPU変換、毎stepの重いログなど、ホストとの同期を減らす。
- `torch.compile`やキャッシュは、初回・再コンパイル費用を残り処理で回収できる場合に使う。
- activation checkpointingはメモリと再計算の交換条件として評価し、毎batchの`empty_cache()`を定石にしない。

具体的な条件、計測方法、一次資料は [GPUガイド](skills/colab-cli-reliable/references/gpu.md) にまとめています。

## TPUを効率よく使う

- 実際のTPU世代・対応フレームワーク・デバイス数を調べる。「TPUは常に8コア」と仮定しない。
- shape・dtype・制御フローを安定させ、可変長データを少数のbucketへまとめる。過大なpaddingも計算コストとして扱う。
- JIT対象をループ外で定義し、不要な再コンパイルを避ける。キャッシュは作成だけでなくhitを確認する。
- BF16等を品質検証と組み合わせ、実デバイスに合うper-device batchを選ぶ。
- 前処理・読み込みを先読みし、ホストへ値を戻す回数を減らす。
- 初回コンパイルと定常実行を分け、非同期計算の完了を待って計測する。
- 分散は実トポロジーと仕事量に見合う場合だけ使い、データ分割とcollectiveを揃える。

上級オプションとして、JAXの**CPU上でのTPU向けクロスコンパイル**も扱っています。通常のCPU JITキャッシュとは異なり、対象トポロジー・版・sharding等を揃えて、TPU側でのcache hitを確認する必要があります。繰り返す既知の仕事向けで、標準手順にはしていません。[TPUガイド](skills/colab-cli-reliable/references/tpu.md)

2026年11月13日時点ではPyTorch TPUの推奨経路にTorchTPUへの変更があります。一方、TensorFlowの対応は世代・PJRT・実ランタイムに依存します。こうした変化は [日付付き互換性メモ](skills/colab-cli-reliable/references/compatibility.md) に隔離し、スキル本体には固定していません。

## Drive等の使い方

Driveには入力原本、準備済みshard、チェックポイント、最終成果物を置きます。大量の小ファイルを毎step直接読む代わりに、必要分をローカルディスクへ配置するか、適切なサイズで先読みします。

保存はコピー後に検証し、完成した世代だけをmanifestから参照します。Drive/FUSE上の複数ファイルrenameを一括で原子的と仮定しません。非同期保存は完了まで待ちます。移動中断による損失や大量I/Oは [Colab公式FAQ](https://research.google.com/colaboratory/faq.html) でも説明されています。

GCS等を使う場合は、ColabのCUとは別にストレージ・API操作・転送費用を確認します。既存の許可と保存先を使い、無断で新しい課金サービスを有効にする手順にはしていません。

## 切断時の扱い

`Connection was lost`、無出力timeout、404、ローカルIDLEだけでは、リモートの処理結果は確定しません。まず **UNKNOWN（結果不明）** とし、元のendpointとjob/attempt IDを保存します。

認証と割当を照合し、小さい進捗・完了ファイルを時間制限付きで確認します。元の処理の停止を確認するまでは再送・同名new・restartを自動実行しません。予算や期限でのキャンセル方針が既にある場合は、それに従って回収・中止・解放します。詳しい現行の不具合、根拠Issue、認証手順は [運用・復旧メモ](skills/colab-cli-reliable/references/operations.md) を参照してください。

## 使い方

```bash
git clone https://github.com/Aero123421/use-google-colab-cli-skills.git
```

エージェントに `skills/colab-cli-reliable/SKILL.md` を読ませるか、使用するエージェントが定めるスキル配置先へ **フォルダ全体** を置いてください。Colab CLIのインストール・アカウント認証は別途必要です。変更しやすいCLIの指定は、運用メモと実際の`--help`で確認します。

依頼例：

> colab-cli-reliableを使って、CPUでの準備からGPU／TPU実行まで進めて。品質条件と処理件数を守り、許可されたCCU・時間予算内で比較して、成果物を検証後にランタイムを解放して。

### CU比較ツール

```bash
python3 skills/colab-cli-reliable/scripts/compare_ccu.py \
  --input skills/colab-cli-reliable/assets/cost-comparison.example.json \
  --max-cus 0.7 --deadline-seconds 1800 --json
```

付属JSONの単価・速度は**すべて架空値**です。実測値に置き換えると、同じ品質・同じ出力件数で比較し、最安と最速を別々に報告します。品質不合格、件数違い、推定費用・時間の上限超過は候補から除外します。Colabへの接続・割当・停止・品質測定・リアルタイム課金制御は行いません。

ローカル検証：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## 情報の扱いとライセンス

技術的な推奨は公式文書・配布物・実装を優先します。GitHub IssueやSNSの一次体験は、再現条件・版・時点を付けた報告として扱い、障害率や固定料金として一般化しません。今回の検証は資料調査、ローカル計算ツールの実行、手順のシナリオ確認までです。実際のアカウント・割当機種での性能は測定していません。

[MITライセンス](LICENSE)。Copyright 2026 Aero123421。参照先のソフトウェア・文書はそれぞれのライセンスに従います。Google Colab CLI本体のコードは同梱していません。
