import json

lines = []
with open(r'C:\Users\Mynest.me\.gemini\antigravity-ide\brain\669466ed-ebd2-4e9c-b877-c5468b54a1ba\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        lines.append(line)

print(f"Total lines: {len(lines)}")

# Let's inspect steps from index 3050 onwards or search for tool calls
for l in lines[-120:]:
    try:
        data = json.loads(l)
        s_idx = data.get("step_index")
        src = data.get("source")
        typ = data.get("type")
        if typ == "PLANNER_RESPONSE":
            tc = data.get("tool_calls", [])
            if tc:
                call_info = ", ".join(f"{c['name']}({list(c.get('args', {}).values())[:2]})" for c in tc)
                print(f"Step {s_idx} [{src}]: {call_info[:150]}")
            elif data.get("content"):
                print(f"Step {s_idx} [{src}]: {data['content'][:150]}")
        elif typ == "USER_INPUT":
            print(f"Step {s_idx} [USER]: {data.get('content', '')[:150]}")
    except Exception as e:
        pass
