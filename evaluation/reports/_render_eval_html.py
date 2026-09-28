from pathlib import Path

import markdown

import sys

name = sys.argv[1] if len(sys.argv) > 1 else "cs_long_scientific_eval_20260923.md"
src = Path(__file__).with_name(name)
html_body = markdown.markdown(
    src.read_text(encoding="utf-8"),
    extensions=["tables", "fenced_code"],
)
page = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>""" + src.stem + """</title>
  <style>
    body { margin: 0; background: #f4f6f8; color: #1b2430; font: 16px/1.65 "Microsoft YaHei", "PingFang SC", sans-serif; }
    main { max-width: 880px; margin: 0 auto; padding: 32px 24px 72px; }
    h1 { font-size: 28px; line-height: 1.3; margin: 0 0 16px; }
    h2 { font-size: 20px; margin: 36px 0 12px; padding-top: 8px; border-top: 1px solid #d5dce3; }
    h3 { font-size: 16px; margin: 24px 0 8px; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0 20px; font-size: 14px; background: #fff; }
    th, td { border: 1px solid #d5dce3; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #eef2f6; }
    blockquote { margin: 10px 0 18px; padding: 10px 14px; background: #fff; border-left: 3px solid #5b6b7c; color: #243040; }
    code, pre { font-family: Consolas, "Sarasa Mono SC", monospace; font-size: 13px; }
    pre { background: #fff; border: 1px solid #d5dce3; padding: 12px; overflow: auto; }
    hr { border: 0; border-top: 1px solid #d5dce3; margin: 28px 0; }
  </style>
</head>
<body>
  <main>
""" + html_body + """
  </main>
</body>
</html>
"""
out = src.with_suffix(".html")
out.write_text(page, encoding="utf-8")
print(out)
