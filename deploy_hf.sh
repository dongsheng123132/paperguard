#!/bin/bash
# 一键重新部署到 Hugging Face Spaces
# 用法: bash deploy_hf.sh
#
# 工作流: 把当前 main 分支的内容(不含 PDF 等二进制) squash 成一个 commit,
# 通过 hf-deploy orphan 分支强推到 hf/main。
# 不影响本地 main 的提交历史。
set -euo pipefail

if [ -z "${HF_TOKEN:-}" ]; then
  echo "❌ 请先设置 HF_TOKEN 环境变量"
  echo "   export HF_TOKEN=hf_xxxxxxxx"
  exit 1
fi

REMOTE_URL="https://hefs:${HF_TOKEN}@huggingface.co/spaces/hefs/paperguard"

# 确保当前在 main 分支
CURRENT=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT" != "main" ]; then
  echo "❌ 当前不在 main 分支(当前: $CURRENT),先 git checkout main"
  exit 1
fi

# 重建 hf-deploy 分支(orphan,无历史)
git branch -D hf-deploy 2>/dev/null || true
git checkout --orphan hf-deploy
git add -A
git commit -m "Deploy $(date +%Y-%m-%d) — $(git -c log.showSignature=false log main -1 --format=%s)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

# 推送到 HF
git remote set-url hf "$REMOTE_URL" 2>/dev/null || git remote add hf "$REMOTE_URL"
git push hf hf-deploy:main --force

# 回到 main
git checkout main
echo ""
echo "✅ 推送完成。Build 状态: https://huggingface.co/spaces/hefs/paperguard"
echo "   直链: https://hefs-paperguard.hf.space (build 完后访问)"
