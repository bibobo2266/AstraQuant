"""Use the authorized GitHub connector for the existing publisher API calls."""
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'AstraQuant-checkout/scripts'))
import run_s3_ab_saved as runner

QUEUE = ROOT / 'github_checkpoint_queue'
QUEUE.mkdir(exist_ok=True)

def connector_api(self, method, path, body=None):
    key = uuid.uuid4().hex
    request = QUEUE / (key + '.request.json')
    response = QUEUE / (key + '.response.json')
    temporary = request.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(method=method, path=path, body=body)))
    temporary.replace(request)
    while not response.exists():
        time.sleep(0.25)
    result = json.loads(response.read_text())
    if 'error' in result:
        raise RuntimeError(result['error'])
    return result['result']

runner.GitHubCheckpointPublisher.api = connector_api
original_publish = runner.GitHubCheckpointPublisher.__call__

def publish_and_report(self, checkpoint):
    cell = Path(checkpoint).parent.name
    previous = self.receipts.get(cell, {}).get('commit')
    receipt = original_publish(self, checkpoint)
    if receipt['commit'] != previous:
        connector_api(self, 'POST', 'issues/6/comments', dict(body=
            'Sol-E｜實讀新 checkpoint 已遠端保存並讀回 manifest：' +
            json.dumps(dict(cell=cell, checkpoint=receipt), ensure_ascii=False) +
            '。本地每日存、遠端每20日存；保存後同一engine直接續跑，無核准暫停。'
            '此為保存日進度，未宣稱全期完成或有持股續跑驗帳通過。'))
    return receipt

runner.GitHubCheckpointPublisher.__call__ = publish_and_report

if __name__ == '__main__':
    # Preserve the already completed B1 day before restarting either round.
    root = ROOT / 'AstraQuant-checkout/results/trading_plan_r1/s3_live_20261011'
    publisher = runner.GitHubCheckpointPublisher(
        token_file=ROOT / '.task_github_token', local_root=root / 'B',
        remote_root='results/trading_plan_r1/s3_live_20261011/B')
    if 'B1' not in publisher.receipts:
        publisher(root / 'B/B1/checkpoint.json')
    # One round at a time. Every 20-day save continues in the same engine;
    # there is no approval pause or repeated source load between saves.
    for round_name in ['A', 'B']:
        sys.argv = [__file__, '--workspace', str(ROOT), '--output', str(root / round_name),
                    '--remote-root', 'results/trading_plan_r1/s3_live_20261011/' + round_name,
                    '--token-file', str(ROOT / '.task_github_token'), '--round', round_name]
        runner.main()
