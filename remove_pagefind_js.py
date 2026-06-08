import re

with open('site/assets/main.js', 'r') as f:
    content = f.read()

# Remove pagefindAvailable
content = re.sub(r'\s*let pagefindAvailable = false;\n', '\n', content)

# Remove initPagefind function entirely
content = re.sub(
    r'\s*// ─── Pagefind Integration ──────────────────────────────────\n\s*async function initPagefind\(\) \{.*?\}\n',
    '\n',
    content,
    flags=re.DOTALL
)

# Remove await initPagefind(); from init()
content = re.sub(r'\s*await initPagefind\(\);\n', '\n', content)

with open('site/assets/main.js', 'w') as f:
    f.write(content)
