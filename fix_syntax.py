import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the literal backslashes
content = content.replace(r"\'db_type\'", '"db_type"')
content = content.replace(r"\'sqlite\'", '"sqlite"')
content = content.replace(r"\'BEGIN IMMEDIATE\'", '"BEGIN IMMEDIATE"')

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
