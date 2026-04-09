# 为 `algokit-example` 做贡献

欢迎任何形式的贡献！每一份贡献都很宝贵，我们会给予致谢。

你可以通过多种方式参与：

# 贡献类型

## 报告缺陷（Bug）

在 `Issues` 提交缺陷：<http://117.78.35.35/guojh/algokit-example/-/issues>

提交缺陷时请包含：

- 你的操作系统及版本。
- 任何有助于排查的本地环境信息。
- 可复现问题的详细步骤。

## 修复缺陷

在 Issues 列表中查找带有“bug”“help wanted”标签的条目，这些都欢迎你来修复。

## 实现新特性

在 Issues 列表中查找带有“enhancement”“help wanted”标签的条目，这些都欢迎你来实现。

## 编写文档

无论是完善官方文档、补充 docstring，还是在博客/文章中介绍，`algokit-example` 都非常欢迎文档贡献。

## 提交反馈

反馈问题或建议：<http://117.78.35.35/guojh/algokit-example/-/issues>

如果你在提议一个新特性：

- 详细说明它应如何工作。
- 尽可能缩小范围，便于实现与评审。
- 记住这是一个社区驱动的项目，欢迎并感谢你的贡献 :)

# 开始上手

准备好贡献了吗？下面是为本地开发设置 `algokit-example` 的步骤。本文档假设你已安装并可使用 `uv` 与 `Git`。

1. 将 `algokit-example` 派生到你的命名空间（或直接在仓库中创建分支）。

2. 克隆你的仓库：

```bash
cd <directory_in_which_repo_should_be_created>
git clone git@117.78.35.35:2222:YOUR_NAME/algokit-example.git
```

3. 进入项目目录并安装依赖环境：

```bash
cd algokit-example
uv sync
```

4. 安装 pre-commit，以在提交时运行格式化/静态检查：

```bash
uv run pre-commit install
```

5. 为本地开发创建分支：

```bash
git checkout -b name-of-your-bugfix-or-feature
```

现在你就可以在本地开始改动了。

6. 别忘了为新增功能在 `tests` 目录中添加测试用例。

7. 完成修改后，先检查格式与静态检查是否通过：

```bash
make check
```

8. 运行单元测试：

```bash
make test
```

9. 在提交合并请求前，建议本地运行 tox（可选）。这会在多个 Python 版本上运行测试：

```bash
tox
```

这需要你在本地安装多个 Python 版本。该步骤也会在 CI/CD 流水线中执行，因此你也可以选择跳过本地执行。

10. 提交并推送你的更改：

```bash
git add .
git commit -m "Your detailed description of your changes."
git push origin name-of-your-bugfix-or-feature
```

11. 在平台上提交合并请求（Merge Request）。

# 合并请求指南

在你提交合并请求之前，请确认符合以下要求：

1. 合并请求应包含相应的测试。

2. 如果合并请求新增了功能，请更新文档：
   将新功能放入带有 docstring 的函数中，并在 `README.md` 中加入该功能的说明。
