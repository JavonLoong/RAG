import os
import time
import zipfile
from glob import glob

log_dir = r'C:\Users\15410\AppData\Local\PowerRAG\current_console\logs'
chroma_dir = r'C:\Users\15410\AppData\Local\PowerRAG\current_console\chroma'
zip_path = r'C:\Users\15410\Desktop\完整的数据库_全量入库完成.zip'

print('开始监控向量入库进程...')
latest_log = max(glob(os.path.join(log_dir, '*process*.log')), key=os.path.getmtime)
print(f'正在监控日志: {latest_log}')

completed = False
while not completed:
    with open(latest_log, 'r', encoding='utf-8') as f:
        content = f.read()
        if '"event": "operation_ok"' in content or '"event": "process_ok"' in content:
            completed = True
            break
    time.sleep(10)
    
print('入库已全部完成！正在打包真实的 ChromaDB 向量库文件...')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(chroma_dir):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, chroma_dir)
            zf.write(full, f'chroma/{arc}')
            
print(f'\n打包成功！文件已保存到桌面: {zip_path}')
print('你可以关闭此窗口了。')
