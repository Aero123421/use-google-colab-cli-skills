# Google Colab CLI 安定運用・CU節約スキル

[English](README.md) · [SKILL.md](skills/colab-cli-reliable/SKILL.md) · [MITライセンス](LICENSE)

Google公式の **google-colab-cli** をAIエージェントから安定運用し、**必要な品質・件数・期限を満たす成果物までの総CU（Compute Units）を最小化**するためのOSSスキルです。

- **作成日時：** `2026年11月13日 18:25:10 JST`（`2026-11-13T09:25:10Z`、初回保存時点）
- **情報確認日：** `2026年11月13日`（CLI／GPU運用の追補反映：`2026年11月16日`）
- **位置づけ：** 公式CLIを使うための独立コミュニティプロジェクト（Google公式スキルやCLI本体ではありません）。調査・検証のためにColabランタイム割当やCU消費は行っていません。

---

## クイックスタート

```bash
git clone https://github.com/Aero123421/use-google-colab-cli-skills.git
```

[`skills/colab-cli-reliable`](skills/colab-cli-reliable/SKILL.md) **フォルダ全体**（`SKILL.md`・`references/`・`scripts/`・`assets/` を揃えたまま）をお使いのエージェントのスキル配置先へコピーするか、エージェントに [SKILL.md](skills/colab-cli-reliable/SKILL.md) を読ませてください。`google-colab-cli` のインストールとアカウント認証は事前前提です（手順は [運用・復旧メモ](skills/colab-cli-reliable/references/operations.md) を参照）。

**依頼例：**

> `colab-cli-reliable` を使って、前処理から許可されたCU・時間予算内でのGPU/TPU実行、切断復旧、成果物の検証、ランタイム解放まで進めて。

---

## 基本ライフサイクル

ハードウェアを変更するとVMは作り直されます。**CPUランタイムの `/content`・導入パッケージ・カーネル状態はGPU/TPUへ引き継がれません**（[Colab開発者の説明](https://github.com/googlecolab/colab-vscode/discussions/265)）。

```text
手元で検証・アーカイブ試験 ─▶ （必要時のみCPU / 永続先受け渡し） ─▶ GPU/TPU新規確保
   ─▶ 実アセット＋1-stepプリフライト ─▶ 学習・検証前保存 ─▶ 救出回収・解放
   ─▶ 対象CPU側でエクスポート・量子化校正・パリティ検証・レポート
```

1. **手元で事前検証する：** データ検証・ハッシュ記録に加え、最小化ソースアーカイブはローカルの一時ディレクトリへ展開して `--help`・import・後段チェック用スクリプトの dry-run まで0 CUで通します。
2. **必要な場合だけ永続保存を経由する：** 手元からDrive等へ直接送れるならColab CPUは省略します（小規模データではGPU確保後の直転送が安い場合もあります）。`colab upload` は常に `/content/` 直下等の既存パスへフラットに送り、サブディレクトリ配置はVM側で行います。
3. **実機確認とプリフライトを通す：** 新規確保したGPU/TPUで実デバイス・トポロジーを確認し、パッケージ名ではなく実際に使うOS資産・フォント・ファイルの読込と、全モデルの1-step forward/backward＋保存・復元テストを先に通します。
4. **保存してから検証する：** 学習完了直後に重みとSHA-256マニフェスト（大容量時は分割チャンク）を確定出力し、その後に下流チェックを置きます。
5. **救出・解放後にCPU処理へ移る：** 正常・異常・タイムアウト・中断いずれの終了でも先に回収可能ファイルを救出し、所有セッション停止→`sessions` 消失確認→`usage` 記録まで完了してから、ONNX変換・INT8量子化校正・実デプロイCPUパリティ検証・単体テスト・可視化をローカルで行います。

---

## 主要ルール

| 領域 | 運用ルール |
| --- | --- |
| **総量コスト比較** | 時間単価ではなく、準備・転送・コンパイル・計算・保存・待機を含む `Σ（CU/時 × 秒数 / 3600）` を同一品質・同一出力件数で比較する。 |
| **ファイル転送** | `colab upload` は未作成サブディレクトリでContents APIが500になり得るため `/content/` へフラット転送する。大容量回収は分割チャンク＋SHA-256マニフェストで行う。 |
| **長時間ジョブ** | 単一WebSocketを数時間維持せず、VM内デタッチ実行（atomic `progress.json` 更新）＋有界周期の軽量監視を使う。停滞（heartbeat）検知と実測スループット基準の動的期限を分離する。 |
| **再開とステージ分割** | 多段パイプラインはステージ単位の検証済みチェックポイントを出し、再実行時は既完了重みを再注入してスキップ可能にする。 |
| **切断復旧（UNKNOWN）** | `exit 0`・ローカル `IDLE`・`colab log` だけで成功判定しない。切断時は `progress.json` と `sessions` を確認し、盲目的な再送や同名 `new` 上書きをしない。 |
| **GPU / TPU / CPU 分担** | アクセラレータは計算と最小保存確認に絞り、エクスポート・量子化校正・厳密CPUパリティ検証（サーバーCPUとデプロイCPUの丸め差対策）・単体テストは解放後へ移す。 |
| **解放確認** | 停止後に `colab --auth=adc sessions` で所有endpointの消失を確認し、`colab --auth=adc usage` を台帳へ記録する（`usage` はアカウント全体値）。 |

具体的な手順・版ごとの制約・一次資料リンクは `references/` へ分離し、[SKILL.md](skills/colab-cli-reliable/SKILL.md) 本体を短く保っています。

---

## ローカル補助ツール

いずれも Python 標準ライブラリのみで動作し、**外部ネットワークや Colab API へは一切接続しません**。

### 1. CU比較ツール（`compare_cu.py`）

記録済みの候補データに対し、品質・厳密出力件数・CU上限・期限で比較します。

```bash
python3 skills/colab-cli-reliable/scripts/compare_cu.py \
  --input skills/colab-cli-reliable/assets/cost-comparison.example.json \
  --max-cus 0.7 --deadline-seconds 1800 --json
```

> **注意：** [cost-comparison.example.json](skills/colab-cli-reliable/assets/cost-comparison.example.json) の単価・時間は**架空の例**です。実測値へ置き換えて利用してください。スキーマ詳細は [cost-and-staging.md](skills/colab-cli-reliable/references/cost-and-staging.md#compare-recorded-candidates-locally) を参照。

### 2. 分割チャンク＋SHA-256マニフェスト（`chunk_manifest.py`）

`colab download` がファイル全量をメモリ上で JSON/Base64 一括処理する制約を補うため、VM側で固定サイズ分割＋SHA-256マニフェスト作成（`split`）を行い、ローカル側で検証・原子的結合（`join`）します。

```bash
python3 skills/colab-cli-reliable/scripts/chunk_manifest.py split --input model.pt --out-dir chunks --chunk-mib 16
python3 skills/colab-cli-reliable/scripts/chunk_manifest.py join --manifest chunks/model.pt.manifest.json --output model.pt
```

---

## ファイル構成

| ファイル | 用途 |
| --- | --- |
| [SKILL.md](skills/colab-cli-reliable/SKILL.md) | エージェント向けの短い12規則本体 |
| [Cost & staging](skills/colab-cli-reliable/references/cost-and-staging.md) | CU計算、CPU引き継ぎ、アーカイブ試験、プリフライト、ステージ再注入、Drive |
| [GPU guide](skills/colab-cli-reliable/references/gpu.md) | プリフライト、スループット、数値確認、保存先行、CPU間丸め差対策 |
| [TPU guide](skills/colab-cli-reliable/references/tpu.md) | トポロジー確認、shape安定化、パイプライン、CPUクロスコンパイル |
| [CLI operations](skills/colab-cli-reliable/references/operations.md) | 日付付きCLI調査・認証・upload/chunk・長時間実行・復旧手順（日本語） |
| [Compatibility](skills/colab-cli-reliable/references/compatibility.md) | 日付付きCLI／フレームワーク互換・TorchTPU移行メモ |
| [compare_cu.py](skills/colab-cli-reliable/scripts/compare_cu.py) / [tests](tests/test_compare_cu.py) | オフラインCU比較ツールと単体テスト |
| [chunk_manifest.py](skills/colab-cli-reliable/scripts/chunk_manifest.py) / [tests](tests/test_chunk_manifest.py) | オフライン分割／検証／結合ツールと単体テスト |

---

## 開発・検証・ライセンス

バイトコードを生成せずにオフラインテストを実行します。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

- **根拠の扱い：** 推奨事項は Colab・Google Cloud・JAX・PyTorch・TensorFlow 等の一次資料を優先し、Issue 報告や実地知見は日付付きの観察事項として区別しています。保守規約は [AGENTS.md](AGENTS.md) を参照してください。
- **ライセンス：** [MITライセンス](LICENSE)（Copyright 2026 Aero123421）。参照先ソフトウェア・文書は各ライセンスに従い、`google-colab-cli` 本体の実装は同梱していません。
