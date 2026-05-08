import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add placeholder = get_placeholder()
content = content.replace('cur = get_cursor(conn)\n', 'cur = get_cursor(conn)\n    placeholder = get_placeholder()\n')
content = content.replace('cur = get_cursor(conn)\r\n', 'cur = get_cursor(conn)\r\n    placeholder = get_placeholder()\r\n')

# Convert execute('...') to execute(f'...')
content = re.sub(r'cur\.execute\(\s*\"', 'cur.execute(f\"', content)
content = re.sub(r'cur\.execute\(\s*\'', 'cur.execute(f\'', content)
content = re.sub(r'cur\.execute\(\s*\"\"\"', 'cur.execute(f\"\"\"', content)

# Convert where_clauses.append('...')
content = re.sub(r'\.append\(\s*\"', '.append(f\"', content)

# Replace '?' with '{placeholder}' EXCEPT in ["?"]
content = content.replace('["?"]', '[placeholder]')
content = content.replace('?', '{placeholder}')

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
