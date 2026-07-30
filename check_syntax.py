import ast
import sys
try:
    with open(r"C:\PROJECTS\newmanim\app\vivacity_character.py", "r", encoding="utf-8") as f:
        content = f.read()
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error: {e}")
    print(f"Line {e.lineno}: {e.text}")
except Exception as e:
    print(f"Other error: {e}")