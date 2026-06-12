import os
import shutil

src_dir = r'd:\虚拟C盘\RAG'
dest_dir = r'd:\虚拟C盘\RAG_中文版'

translation_map = {
    'api_server': '01_API后端服务',
    'configs': '02_系统配置',
    'core_domain': '03_核心领域实体',
    'data_pipeline': '04_数据处理流水线',
    'docs': '05_项目文档',
    'evaluation': '06_评测系统',
    'experiments': '07_实验记录',
    'frontend_app': '08_前端控制台界面',
    'kg_pipeline': '09_知识图谱抽取流水线',
    'model_adapters': '10_大模型接口适配',
    'observability': '11_日志与系统监控',
    'rag_orchestrator': '12_RAG核心编排引擎',
    'retrieval_engine': '13_混合检索引擎',
    'scripts': '14_辅助执行脚本',
    'storage_layer': '15_数据存储层',
    'tests': '16_自动化测试',
    'tools': '17_实用工具',
    'archive': '18_历史归档',
    'RAG_JSON_Files': '19_RAG_JSON数据',
    'RAG_github_pages_publish': '20_Github_Pages发布页',
    'RAG_main_sync_worktree': '21_主分支同步工作区',
    'README.md': '00_项目说明.md',
    'TECH_STACK.md': '00_技术栈说明.md',
    'CONTRIBUTING.md': '00_参与贡献指南.md',
    'CONTRIBUTING-zh.md': '00_参与贡献指南_中文.md',
    'OFFLINE_DEPLOYMENT_NOTICE.md': '00_离线部署注意事项.md',
    'LLM_Context.md': '00_大模型上下文背景.md'
}

ignore_dirs = {'.git', '.venv', '.pytest_cache', '__pycache__', 'RAG_main_sync_worktree', 'RAG_github_pages_publish'}

if os.path.exists(dest_dir):
    shutil.rmtree(dest_dir)

os.makedirs(dest_dir)

for item in os.listdir(src_dir):
    if item in ignore_dirs:
        continue
    
    src_path = os.path.join(src_dir, item)
    # 只翻译根目录的文件和文件夹名称
    new_name = translation_map.get(item, item)
    dest_path = os.path.join(dest_dir, new_name)
    
    try:
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path, ignore=shutil.ignore_patterns(*ignore_dirs), ignore_dangling_symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(src_path, dest_path)
    except Exception as e:
        print(f"Skipping {src_path} due to error: {e}")

print(f'成功复制并重命名到: {dest_dir} (仅翻译顶层目录和核心文档，子文件名保持纯英文)')
