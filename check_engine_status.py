import urllib.request
import json

state = json.loads(urllib.request.urlopen('http://localhost:8000/api/state').read())
print('profit_threshold_pct in state:', state.get('profit_threshold_pct'))
print('positions:', state.get('positions'))
print('available_capital:', state.get('available_capital'))
print('total_capital:', state.get('total_capital'))
print('engine_status:', state.get('engine_status'))
print('signals count:', len(state.get('signals', [])))
for s in state.get('signals', []):
    print(f"  {s.get('symbol')}: signal={s.get('signal')}, pred_ret={s.get('predicted_return_pct')}%, conf={s.get('confidence')}%, hurdle={s.get('profit_threshold_pct')}%")
