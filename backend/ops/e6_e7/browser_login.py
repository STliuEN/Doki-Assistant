"""Verify the authorized security account through the existing Playwright CLI tab."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    private = json.loads((ROOT / ".runtime/e6e7-target-closure-20260914/security-admin.private.json").read_text(encoding="utf-8"))
    bins = list((Path.home() / "AppData/Local/npm-cache/_npx").glob("*/node_modules/@playwright/cli/playwright-cli.js"))
    assert bins
    screenshot = ROOT / "output/playwright/e6e7-security-admin.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    code = (
        """async (page) => {
        await page.getByRole('textbox', {name:'用户名',exact:true}).fill(USERNAME);
        await page.getByRole('textbox', {name:'密码',exact:true}).fill(PASSWORD);
        await page.getByRole('button', {name:'登录',exact:true}).click();
        await page.waitForURL(url => !url.pathname.includes('login'));
        await page.screenshot({path: SCREENSHOT, fullPage:true});
        return {url:page.url(), loginSucceeded:true};
    }""".replace("USERNAME", json.dumps(private["username"]))
        .replace("PASSWORD", json.dumps(private["password"]))
        .replace("SCREENSHOT", json.dumps(str(screenshot)))
    )
    completed = subprocess.run(["C:/nvm4w/nodejs/node.exe", str(bins[0]), "-s=e6e7closure", "run-code", code], capture_output=True)
    output = completed.stdout.decode("utf-8")
    # CLI echoes its script. Retain only the returned JSON, never the login script.
    if completed.returncode or "### Error" in output or "### Result" not in output:
        raise RuntimeError("Browser login verification failed; inspect tab without exposing credentials")
    value = json.loads(output.split("### Result", 1)[1].split("###", 1)[0].strip())
    assert value["loginSucceeded"]
    (ROOT / ".runtime/e6e7-target-closure-20260914/browser-login.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps(value))


if __name__ == "__main__":
    main()
