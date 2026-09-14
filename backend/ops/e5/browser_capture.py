"""Persist Playwright CLI evidence without exposing authentication storage."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "name",
        choices=[
            "queued",
            "building",
            "failed",
            "ready",
            "query-saved",
            "index-queued",
            "restarted",
            "api-restarted",
            "chunks",
            "upload",
            "uploaded",
        ],
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--edit", action="store_true")
    args = parser.parse_args()
    # Use the installed CLI's actual bin, avoiding cmd.exe's quote rewriting.
    cache = Path.home() / "AppData/Local/npm-cache/_npx"
    packages = list(cache.glob("*/node_modules/@playwright/cli/playwright-cli.js"))
    if not packages:
        raise RuntimeError("Initialize Playwright CLI through npx first")
    command = ["C:/nvm4w/nodejs/node.exe", str(packages[0]), "-s=e5-acceptance"]
    if args.reload:
        subprocess.run([*command, "reload"], capture_output=True, check=True)
    screenshot = ROOT / "output/playwright" / ("e5-" + args.name + ".png")
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    code = """async (page) => {
      const status = page.getByTestId('rag-status');
      await status.waitFor({state:'visible'});
      ACTION
      const actual = await status.getAttribute('data-status');
      await page.screenshot({path: SCREENSHOT, fullPage: true});
      return {url:page.url(), state:actual, text:await status.innerText(),
        top_k:await page.getByRole('spinbutton',{name:'返回条数',exact:true}).inputValue(),
        chunk_size:await page.getByRole('spinbutton',{name:'每段字符数',exact:true}).inputValue(),
        index_edit_disabled:await page.getByRole('spinbutton',{name:'每段字符数',exact:true}).isDisabled()};
    }""".replace("SCREENSHOT", json.dumps(str(screenshot)))
    action = ""
    if args.edit and args.name == "query-saved":
        action = """await page.getByRole('spinbutton',{name:'返回条数',exact:true}).fill('3');
          await page.getByRole('button',{name:'保存检索设置',exact:true}).click();
          await page.getByText('检索设置已保存',{exact:true}).waitFor();
          await page.reload(); await page.getByTestId('rag-status').waitFor();"""
    if args.edit and args.name == "index-queued":
        action = """await page.getByRole('spinbutton',{name:'每段字符数',exact:true}).fill('800');
          await page.getByRole('button',{name:'保存切片并重建',exact:true}).click();
          await page.getByText('重建请求已登记，请等待索引就绪',{exact:true}).waitFor();
          await page.reload(); await page.getByTestId('rag-status').waitFor();"""
    code = code.replace("ACTION", action)
    if args.name == "chunks":
        code = """async (page) => {
          await page.getByText('e5-acceptance.txt',{exact:true}).click();
          await page.getByRole('dialog').waitFor();
          await page.getByRole('button',{name:/文档片段/}).click();
          await page.getByRole('dialog').getByText('紫色水獭',{exact:false}).waitFor();
          const label = await page.getByRole('button',{name:/文档片段/}).innerText();
          await page.screenshot({path: SCREENSHOT, fullPage:true});
          await page.keyboard.press('Escape');
          return {chunks_label:label, verified_chunk_visible:true};
        }""".replace("SCREENSHOT", json.dumps(str(screenshot)))
    if args.name in {"upload", "uploaded"}:
        file = args.directory.resolve() / "e5-browser-upload.txt"
        if args.name == "upload":
            file.write_text("橙色海鹅是 E5 浏览器上传验收样本，仅存于隔离验收数据库。", encoding="utf-8")
        if args.name == "upload" and args.edit:
            subprocess.run(
                [*command, "run-code", "async (page) => { await page.getByRole('button',{name:'上传文档',exact:true}).click(); }"],
                capture_output=True,
                check=True,
            )
            subprocess.run([*command, "upload", str(file)], capture_output=True, check=True)
        upload_action = (
            """await page.getByText('已进入索引队列',{exact:true}).waitFor();
          await page.getByText('等待构建',{exact:true}).waitFor();"""
            if args.name == "upload"
            else "await page.getByText('索引已就绪',{exact:true}).waitFor();"
        )
        code = (
            """async (page) => {
          ACTION
          await page.screenshot({path:SCREENSHOT, fullPage:true});
          return {state:await page.getByTestId('rag-status').getAttribute('data-status'),
            queued_message:await page.getByText('已进入索引队列',{exact:true}).count(),
            ready_message:await page.getByText('索引已就绪',{exact:true}).count()};
        }""".replace("ACTION", upload_action)
            .replace("FILE", json.dumps(str(file)))
            .replace("SCREENSHOT", json.dumps(str(screenshot)))
        )
    value = subprocess.run([*command, "run-code", code], capture_output=True, check=True)
    output = value.stdout.decode("utf-8")
    if "### Result" not in output or "### Error" in output:
        raise RuntimeError("Browser capture did not return evidence; inspect the active modal/page")
    (args.directory / ("browser-" + args.name + ".txt")).write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
