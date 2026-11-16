# Colab CLI 運用・復旧メモ

確認日: 2026-11-13 JST（2026-11-16 JST に `v0.8.0..main` の Contents API・`execution.py`・`runtime.py`・`consumption.py` および長時間運用の実地報告を反映）。Google公式 `googlecolab/google-colab-cli` を対象とする。公式配布wheel、タグ、main、Issue/PR、一次の利用報告を照合した。利用者のColabアカウントでログイン・VM割当・実行試験を行った結果ではない。

この資料は日付付きの実装・障害調査。普遍的な短い実行規則は [SKILL.md](../SKILL.md)、CPUからGPU/TPUへの引き継ぎ・総CU計算・Driveは [cost-and-staging.md](cost-and-staging.md)、TPUの現行バックエンド対応は [compatibility.md](compatibility.md) を参照する。新しい版を採用するときは以下の未解決状態とCLIの実際のhelpを再確認する。

## 目次

- [版と未解決事項](#版と未解決事項)
- [認証と準備](#認証と準備)
- [ジョブと完了記録](#ジョブと完了記録)
- [切断時の復旧](#切断時の復旧)
- [ファイルとDrive](#ファイルとdrive)
- [並列と割当](#並列と割当)
- [導入時の確認試験](#導入時の確認試験)

## 版と未解決事項

PyPI最新は **0.8.0**。wheel公開は2026-11-10 19:42 UTC、**11月11日04:42 JST**。Python >=3.12、依存 `jupyter-kernel-client==0.9.0`。タグは `v0.8.0` / `6045e34`。初回調査時mainは `10f442a96fd91143bcbe7675af0272cfba8f2b06`、2026-11-16 JST 再確認時点でもタグ最新は `v0.8.0`（`main` 先頭は `02d2321`、追加された `#235`・`#234`・`#246`・`#245` に `contents.py` への変更はない）。GitHub Releasesは空、CHANGELOGの版見出しも古いため、最新版はPyPIと配布物で判断する。[PyPI](https://pypi.org/project/google-colab-cli/0.8.0/) / [公開時刻のJSON](https://pypi.org/pypi/google-colab-cli/0.8.0/json)

| 項目 | 確認した状態 | 判断 |
| --- | --- | --- |
| 切断後に元の出力・結果を回収できない | [#220](https://github.com/googlecolab/google-colab-cli/issues/220)、11/7、Open | 同一kernelで処理が完了した実験あり。通信失敗と実行失敗を区別する |
| journalとresumeによる復旧 | [PR #221](https://github.com/googlecolab/google-colab-cli/pull/221)、Open | 提案段階。標準コマンドとして使わない |
| Pythonエラーでもexecがexit 0 | [PR #237](https://github.com/googlecolab/google-colab-cli/pull/237)、11/11、Open | 提案の `--json` は未提供。自前の完了記録で判定する |
| OAuth部分同意で約1時間ごとに再認証 | [#116](https://github.com/googlecolab/google-colab-cli/issues/116) | 0.8.0にも該当実装が残る。ADC経路でこの不具合を避ける |
| 部分同意の修正 | [PR #235](https://github.com/googlecolab/google-colab-cli/pull/235)、11/13 04:14 JST mainへmerge | 0.8.0に未収録。メンテナーは0.8.1予定と説明。公開を再確認する |
| 古いruntime proxy tokenで約1時間後に操作不能 | [#140](https://github.com/googlecolab/google-colab-cli/issues/140)、9/27 Closed | メンテナーが0.7.4への更新を案内。現行のWebSocket結果回収問題と区別する |
| 無出力timeout | [実行仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/02_execution_and_interactive.md) | 現行exec/runは既定30秒のidle timeout。0は無効化。kernel-clientの版とCLIの版を混同しない |

上記runtime、exec/run、Contents APIの主要コードは `v0.8.0..main` に差分がないことを確認した。公式同梱skillにも古い認証・復旧記述がある。READMEやPRの文例を無条件で採用しない。

## 認証と準備

導入例。既存ジョブの実行中には更新しない。

```bash
uv tool install 'google-colab-cli==0.8.0'
command -v colab
colab version
colab exec --help
colab run --help
```

Python要件を満たす環境を使い、PATH上の別インストールを混同しない。0.8.0はLinux/macOSが公式対象。版を変えるときは未解決事項と実際のhelpを再確認する。

初回のみ、人が認可を行えるターミナルでADCを準備する。

```bash
gcloud auth application-default login \
  --no-launch-browser \
  --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory
```

ヘッドレス用の例。表示URLを信頼できる端末で開き、画面に従って認可コードを元のターミナルへ入力する。コードを会話へ貼らない。既に正しいADCがあるなら再認証は不要。

その後、VMを割り当てずに確認する。

```bash
colab --auth=adc whoami
colab --auth=adc sessions
colab --auth=adc usage
```

`whoami` は0.8.0のhidden commandで、認証をrefreshしアカウントとscopeを確認できる。`sessions` だけでは一部認証失敗が空一覧に見えるコード経路がある。`GOOGLE_APPLICATION_CREDENTIALS` が別identityを指していないか、秘密値を出さずに設定元を確認する。

| 認証 | 対象と注意 |
| --- | --- |
| `gcloud auth application-default login` | 手元のCLIがColab APIへアクセスするADC。`gcloud auth login` とは別 |
| `colab --auth=adc ...` | 毎回明示。グローバルオプションなのでサブコマンドの前 |
| `colab auth -s NAME` | VM内のGCPサービス利用認証。手元のCLIの401修復に使わない |
| `colab drivemount -s NAME` | VMへのDriveマウント。同意URLとEnter入力が必要になり得る |

READMEはadc既定と記載するが、0.8.0の [cli.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/cli.py) はoauth2既定。OAuth keyringはLinuxのロック解除や保存失敗で停滞・毎回再認証になり得る。読み書きには各30秒のtimeoutがあるが、その後の認可コード入力待ちまで非対話で終了する保証はない。

必要scopeは [公式認証仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md) を参照する。ADC選択順は [Google ADC仕様](https://docs.cloud.google.com/docs/authentication/application-default-credentials)、loginは [gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/login) を使う。ADCを選べることと、個人Colabをサービスアカウントで利用できることを同一視しない。

## ジョブと完了記録

以下は推奨設計。Colab CLIの標準機能ではない。

- ジョブごとに `job_id`、試行ごとに `attempt_id` を持たせ、session名、endpoint、コードと入力manifestのhashをローカル台帳（ledger JSON）に記録する。tokenは記録しない。
- `/content/jobs/<job_id>/` に小さい `progress.json`、`result.json`、ログ、成果物を置く。過去の成功記録を今回の成功と取り違えない。
- `progress.json` は時刻（heartbeat）・step・実測スループット（例: `steps/sec`）・最終checkpointを含める。JSONはVMローカルで一時ファイルから `os.replace` 等でatomic renameして確定する。
- **保存・確定を後段検証より必ず先に置く**: 学習ループ完了直後に、後段のエクスポート・パリティ検証・`pytest`・プロヴェナンス検査より **先に** 最終チェックポイント・重み・SHA-256マニフェスト（および大容量時の分割チャンク）を確定出力する。後段検証の例外や数値差で学習済み重みを失わない構造にする。
- `result.json` は同じjob/attemptとコード/入力識別、`succeeded` または `failed`、終了コード、成果物のサイズ・hashを含める。全出力の確定後に成功記録を作る。例外も失敗記録に残すが、記録がなければ結果不明とする。
- checkpointには必要に応じoptimizer、scheduler、step、乱数状態も保存する。複数ステージを直列実行する場合は、ステージごとに検証済みチェックポイントとマニフェストを出し、後半失敗時の再実行では完了済み重みを再注入して既完了ステージをスキップ可能にする。検証したVM外の保存先へ定期コピーし、転送途中のcheckpointは完成版として公開しない。
- `exec -f` はローカルのソースをkernelへ送る。隣接データやモジュールの転送、`__file__`、通常のスクリプト引数を自動再現するとは考えない。ファイル・cwd・依存を明示する。また送信用に最小化したソースアーカイブ／tarballを用意する場合は、**VM確保前にローカルの一時ディレクトリへ展開して `--help`・import・学習後に走る補助スクリプトまで含めた dry-run** を通し、同梱漏れを0 CUで潰す。

重要ジョブは既存割当のない一意の名前で `new`、環境構築・プリフライト確認のうえで実行する。`v0.8.0` の [runtime.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/runtime.py)（`_execute_streaming`）は1回の `exec`/`run` 中1本のWebSocketに依存し、途中の瞬断で `Connection was lost.` になり得る（[#220](https://github.com/googlecolab/google-colab-cli/issues/220)）。また [session仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/01_session_management.md) のとおり runtime proxy token は1時間で期限切れになり、長期接続中の再送はされない。

- **短〜中時間ジョブ**: `exec --timeout 0`（または見合いの `--timeout`）を使い、元の `exec` を外側の短い tool timeout で kill せず `progress.json` を別経路で確認する。timeoutはCLI側の無出力待ち上限であり、WebSocket障害、認可待ち、VM最大寿命とは別。
- **数時間超の長時間ジョブ**: 単一WebSocketを数時間張り続ける代わりに、**VM側でデタッチドワーカー（`start_new_session=True` で `progress.json` のatomic更新とログ出力を継続）を起動し、ローカル側監視プロセスが 60〜90 秒間隔などの有界周期で軽量な生存・進捗確認（`download` による `progress.json` 取得や `sessions` 照合）を行うハイブリッド構成**を推奨する。ローカルtmuxは親shell切断対策、リモートtmux/nohupはshell切断対策でありVM回収対策ではない。またColab公式仕様上、VMの維持はアクティブな実行・対話に依存するため完全放置はアイドル回収リスクがある（ただしダミー処理による保持はしない）。
- **タイムアウトの2層分離と動的ステージ期限**: `progress.json` の更新時刻・`step` が進まない **停滞（stall/heartbeat）検知** と、**ステージ全体の完了期限（deadline）** を分離する。ステージ期限は `3600s` のような短い固定値で決め打ちせず、序盤ウォームアップ後の実測スループット（`steps/sec`）から残り見込み時間×安全係数（例: `1.5〜2.0` 倍）＋保存バッファとして算出し、全体のCU／時間予算上限の範囲内で設定する。

### 終了時クリーンアップ・解放の自動化（台帳記録）

ジョブが正常終了したときはもちろん、例外発生・監視タイムアウト（中止ポリシー発火）・手動中断の終了パス（オーケストレータの `finally` 等）でも、以下の一連確認を順に実行しローカル台帳JSONへ記録する。

1. **救出優先（rescue download）**: スクリプトの終了コードが非ゼロやタイムアウトであっても、まず完了済み／中間チェックポイントとログの有無を確認し、存在すればローカルへ退避して SHA-256 を照合する。
2. **所有セッション停止**: 自分が起動したセッション名に対して `colab --auth=adc stop -s <SESSION_NAME>` を実行する（未確定な一時通信断でリモートが生存中の可能性があり、かつ即時停止ポリシーでない場合を除く）。
3. **割当消失確認**: `colab --auth=adc sessions` に該当セッション／endpoint が残っていないことを確認する。
4. **消費レート確認**: `colab --auth=adc usage` を確認し台帳へ記録する。他に起動中セッションがない単独アカウント運用では `Usage rate: 0.00/hr`・`Active assignments: 0` への復帰を確認する（[consumption.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/consumption.py) のとおり `usage` はアカウント全体表示のため、他セッション併存時はその旨を記録する）。

### 成功判定に使ってはいけないもの

- **execの終了コード0だけ**: Python例外でも0になり得る。Notebookではエラー後のセルも進み得る。
- **statusのIDLEだけ**: [session.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/commands/session.py) はローカル `s.running` を参照し、[execution.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/commands/execution.py) は切断時にもfinallyでこれを消す。
- **colab logだけ**: サーバの完全なjournalではない。execution履歴は処理呼出しが戻った後に記録されるため、切断で最後の出力が欠け得る。
- **CLIプロセスが消えたこと**: リモート停止もVM解放も保証しない。`run` の通常の例外終了は自動解放を試み、SIGKILLはfinallyを飛ばし得る。

## 切断時の復旧

1. 一時的な通信断・WebSocket切断時は状態をUNKNOWNにし、元のsession名・endpoint・job/attemptを保持する。
2. 認証エラーなら `colab --auth=adc whoami` を確認し、`colab --auth=adc sessions` で元endpointの割当を照合する。ローカルsession設定を消さない。404だけでファイルやVMの消失を確定しない。
3. `download -s NAME` で小さい `progress.json` / `result.json` を取得する。Contents APIなのでbusyなkernelへコードを追加する必要がない。1回の読み取りにはprocess timeout等を付け、少数回のbackoff後も不明ならそのまま報告する。
4. 同じjob/attemptの成功記録や保存済みチェックポイントがあれば、まず成果物・中間チェックポイントを救出回収して SHA-256 検証する。失敗記録があれば原因とcheckpointから再開可能性を判断する。
5. 元ジョブの停止を確定できた場合に限り、冪等性とcheckpoint（および完了済みステージの再注入可否）を確認して再開する。元VMの消失が確認できた場合は新しい試行を記録する。同一セッション名での `new` 再利用はしない。
6. 継続監視せず中止・期限切れとして打ち切る方針が設定されている場合は、まず手順4の救出回収を済ませたうえで上記「終了時クリーンアップ・解放」へ進む。未確定のまま無期限放置せず、残るsession・資源消費・次の確認期限を明示する。

`run` は `--keep` がないと監視エラー時にもfinallyでVMを解放する。[run仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/05_run_command.md) と [#220](https://github.com/googlecolab/google-colab-cli/issues/220) を参照。`run --keep` でも出力回復が保証されるわけではない。

## ファイルとDrive

0.8.0（および `main` 確認時点）の [ContentsClient](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/contents.py) はファイル全量をメモリ上で読み、JSON/base64で一括転送する。directory downloadや再開可能なstream転送ではない。requestsにはtimeout指定がなく、control-planeのtimeout環境変数だけでは有界にならない。

- **未作成サブディレクトリ宛 `colab upload` の失敗回避**: `ContentsClient.upload()` は親ディレクトリを事前作成せずに `PUT /api/contents/<path>` を送り、`_request()` は `404` だけを `FileNotFoundError` に変換して他は `raise_for_status()` する実装になっている。実運用報告でも、未作成サブディレクトリ（例: `/content/sub/file`）へ直接 `colab upload` した際、Jupyter `/api/contents` API が `404` ではなく `500 Internal Server Error` を返して失敗した。**アップロード先は常に `/content/<flat_name>` のように既存ディレクトリ直下へフラットに統一し、サブディレクトリ作成・配置・展開は VM 側のセットアップスクリプトで行う。**
- **大容量成果物の分割チャンク＋SHA-256 マニフェスト回収**: `ContentsClient.download()` もファイル全体をメモリ上で JSON + Base64 処理するため、数十 MB 以上の学習済み重み等を一括 `download` すると失敗・タイムアウトしやすい。VM 側で固定サイズ（例: 16〜24 MiB）の分割チャンクと `manifest.json`（全体 SHA-256、総バイト数、各チャンクの SHA-256・バイト長）へ分割出力してからチャンクごとに `colab download` し、ローカル結合後に SHA-256 一致を検証してから採用する。標準ライブラリのみで動作する同梱の [chunk_manifest.py](../scripts/chunk_manifest.py) を VM 側（`split`）とローカル側（`verify` / `join`）の両方で利用できる。
- 大量入力データは `/content` 等へアーカイブ/分割して展開する。既に認証済みの保管先を使う場合も容量・転送失敗を確認する。
- downloadの404はproxy認証エラーが誤分類される場合がある。同一割当の照合と認証更新を先に試す。
- [files.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/commands/files.py) のeditはdownloadの全例外を握りつぶし、空ファイルから編集を始める。自動処理ではdownload成功確認→編集→uploadを使う。
- Drive同意と読み書きを学習前に終える。[#103](https://github.com/googlecolab/google-colab-cli/issues/103) の投稿者はauthuser修正説とincognito回避策を撤回した。最後に確認された手順は、通常ブラウザのaccount chooserでwhoamiと同じアカウントを明示的に選び、許可後にEnter。
- [#113](https://github.com/googlecolab/google-colab-cli/issues/113) は別の約120秒mount失敗報告。古い開発版での報告で現在もOpenだが、0.8.0での再現を今回確認したわけではない。原因仮説を確定事項にしない。
- [公式FAQ](https://research.google.com/colaboratory/faq.html) は大量ファイルや多数の小さいI/Oによる失敗を説明している。Drive容量が大きくてもVMディスクやI/O安定性は増えない。Driveから大量小ファイルを直接読む代わりにVMへ展開する。移動中断でデータを失わないようコピーを検証してから整理する。

## 並列と割当

`--config` はsession metadataのパスだけを変える。settings、history、OAuth keyringまで隔離しない。stateのfile lockもkernel操作の排他制御ではない。同じsessionのexec/install/restart/stopは一つの担当で管理する。[common.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/common.py) / [state.py](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/state.py)

同名newは既存VMへ再接続する操作ではない。新規割当でローカルの名前対応を上書きし、旧VMを取り残し得る。割当API timeout後はserver側の割当を確認する。CLI自身も一部5xxをbackoff付きで再試行するため、外側の無限retryを重ねない。[session仕様](https://github.com/googlecolab/google-colab-cli/blob/main/docs/01_session_management.md)

[#236](https://github.com/googlecolab/google-colab-cli/issues/236) は11/11、有料ユーザーの「G4だけ48時間503、A100は成功」という報告。容量不足は推測であり公式な原因確定ではない。GPU変更は許可済み範囲で行う。[#209](https://github.com/googlecolab/google-colab-cli/issues/209) の無料GPU枠の報告が示すように、usageのCU残高/消費率から無料GPUの残り時間や供給を推定しない。

公式FAQではVM寿命、アイドル、GPU供給は動的。有料でも永続VMにはならない。Pro+の最長24時間も条件付き上限であり保証ではない。正のCU残高がない無料ランタイムのSSH等には別の制限があるため、公式CLIにsshコマンドがあることだけで全tierの利用条件を推定しない。[公式FAQ](https://research.google.com/colaboratory/faq.html)

## 導入時の確認試験

実際に利用する版・アカウント・agent環境で行う受入条件。今回の調査で実施済みではない。VM実行が依頼された範囲で必要最小限のCPU/GPUを用いる。

| 試験 | 確認する結果 |
| --- | --- |
| 短い成功/例外ジョブ | 完了記録で成功/失敗を区別し、execのexit 0を誤判定しない |
| アーカイブとプリフライト | 送信用tarballのローカル展開dry-run、実アセット読込、1-step保存が通る |
| フラット転送とチャンク回収 | `/content/` 直下upload→配置、および分割download結合後のSHA-256一致を確認する |
| 長い無出力・長時間監視 | CLI idle timeoutとデタッチ/定期進捗確認・動的期限を区別する |
| 一時的なクライアント切断 | 元ジョブを再送せず同じjob/attemptの記録で結果を確認する |
| 非ゼロ終了時レスキュー | 後段検証が失敗しても先に保存済みcheckpointを救出しハッシュ検証できる |
| 1時間を越えた同一VMの読み取り | 実環境の認証refreshとproxy期限更新を確認する |
| 中間checkpoint・ステージ再開 | 完了済み重みの再注入によるスキップとcode/inputの整合を確認する |
| 最終回収と解放 | VM外のhash一致、`sessions` 消失、`usage` 確認と台帳記録を確認する |

[Redditの約1時間切断](https://www.reddit.com/r/GoogleColab/comments/1wbh7kf/colab_cutting_after_1_hour_on_colab_cli/) は歴史的な利用報告。[agent連携の感想](https://www.reddit.com/r/ClaudeCode/comments/1u0a2qn/colab_cli_might_quietly_change_how_i_use_coding/) は便利さへの評価であり稼働率測定ではない。古い個別パッチや第三者skillを無検証で導入しない。
