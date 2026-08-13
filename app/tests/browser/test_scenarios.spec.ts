import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import YAML from 'yaml';

type ScenarioStep =
  | { click: { role?: 'button' | 'link'; name?: string; title?: string; testId?: string } }
  | { select_file: { path: string } }
  | { type_editor: { text: string } }
  | { type_input: { value: string } }
  | { fill: { placeholder: string; value: string } }
  | { rename_file: { old_path: string; new_path: string } }
  | { upload_asset: { path: string } }
  | { upload_knowledge: { path: string } }
  | { open_file_references: { path: string } }
  | { assert_visible: { label?: string; title?: string; testId?: string } }
  | { assert_file_contains: { path: string; text: string } };

type ScenarioAssert =
  | { visible: { label?: string; title?: string; testId?: string } }
  | { file_contains: { path: string; text: string } }
  | { file_exists: { path: string } };

type Scenario = {
  id: string;
  name: string;
  dataset: string;
  status: 'active' | 'planned';
  intent?: string;
  steps?: ScenarioStep[];
  asserts?: ScenarioAssert[];
};

type BrowserScenarioFile = {
  scenarios: Scenario[];
};

function loadScenarios(): Scenario[] {
  const yamlPath = new URL('./scenarios.yaml', import.meta.url);
  const raw = readFileSync(yamlPath, 'utf-8');
  const parsed = YAML.parse(raw) as BrowserScenarioFile;
  return parsed.scenarios ?? [];
}

function fileNodeTestId(filePath: string): string {
  return `file-node:${filePath}`;
}

function wikiNodeTestId(nodePath: string): string {
  return `wiki-node:${nodePath}`;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function typeInEditor(page: Page, text: string) {
  await page.waitForTimeout(1000);
  await page.evaluate((nextText) => {
    const hook = window.__DEEPMEMO_TEST__?.setEditorValue;
    if (!hook) {
      throw new Error('DeepMemo editor state hook is not available');
    }
    hook(String(nextText));
  }, text);
  await page.waitForTimeout(500);
}

function fileTree(page: Page) {
  return page.locator('nav[aria-label="data 文件树"]');
}

function fileTreeNode(page: Page, filePath: string) {
  const tree = fileTree(page);
  return tree.locator(`[data-node-path="${filePath}"]`).first();
}

async function waitForFileNode(page: Page, filePath: string) {
  await page.waitForFunction(
    (targetPath) => {
      const tree = document.querySelector('nav[aria-label="data 文件树"]');
      return Boolean(tree?.querySelector(`[data-node-path="${targetPath}"]`));
    },
    filePath,
  );
}

async function revealFilePath(page: Page, filePath: string) {
  const segments = filePath.split('/');
  let current = '';
  for (const segment of segments.slice(0, -1)) {
    current = current ? `${current}/${segment}` : segment;
    await waitForFileNode(page, current);
    const folderByPath = fileTreeNode(page, current);
    const folderByName = fileTree(page).getByRole('button', { name: new RegExp(`^${escapeRegExp(segment)}$`) });
    const folder = (await folderByPath.count()) ? folderByPath : folderByName;
    if (await folder.count()) {
      await expect(folder).toBeVisible();
      await folder.click({ force: true });
      await page.waitForTimeout(100);
    }
  }
}

async function runScenario(page: Page, scenario: Scenario) {
  await page.goto('/');
  await expect(page.getByLabel('DeepMe 首页')).toBeVisible();

  for (const step of scenario.steps ?? []) {
    if ('click' in step) {
      const { role, name, title, testId } = step.click;
      if (testId) {
        await page.getByTestId(testId).click({ force: true });
      } else if (title) {
        await page.getByTitle(title).click({ force: true });
      } else if (role && name) {
        await page.getByRole(role, { name }).click({ force: true });
      } else if (name) {
        await page.getByRole('button', { name }).click({ force: true });
      }
      continue;
    }

    if ('select_file' in step) {
      await revealFilePath(page, step.select_file.path);
      await waitForFileNode(page, step.select_file.path);
      const fileNode = fileTreeNode(page, step.select_file.path);
      if (!(await fileNode.count())) {
        const fileName = step.select_file.path.split('/').pop() ?? step.select_file.path;
        const fallback = fileTree(page).getByRole('button', { name: new RegExp(`^${escapeRegExp(fileName)}$`) });
        await expect(fallback).toBeVisible();
        await fallback.click({ force: true });
        continue;
      }
      await expect(fileNode).toBeVisible();
      await fileNode.click({ force: true });
      continue;
    }

    if ('type_editor' in step) {
      await typeInEditor(page, step.type_editor.text);
      continue;
    }

    if ('type_input' in step) {
      await page.locator('textarea').fill(step.type_input.value);
      continue;
    }

    if ('fill' in step) {
      await page.getByPlaceholder(step.fill.placeholder).fill(step.fill.value);
      continue;
    }

    if ('rename_file' in step) {
      const node = page.getByTestId(fileNodeTestId(step.rename_file.old_path));
      await node.click({ button: 'right' });
      continue;
    }

    if ('upload_asset' in step) {
      await page.setInputFiles('input[type="file"]', path.resolve(path.dirname(new URL(import.meta.url).pathname), step.upload_asset.path));
      continue;
    }

    if ('upload_knowledge' in step) {
      await page.setInputFiles(
        'input[aria-label="上传知识文件"]',
        path.resolve(path.dirname(new URL(import.meta.url).pathname), step.upload_knowledge.path),
      );
      continue;
    }

    if ('open_file_references' in step) {
      await page.getByLabel('引用来源').click();
      continue;
    }

    if ('assert_visible' in step) {
      const { label, title, testId } = step.assert_visible;
      if (testId) {
        await expect(page.getByTestId(testId)).toBeVisible();
      } else if (title) {
        await expect(page.getByTitle(title)).toBeVisible();
      } else if (label) {
        await expect(page.getByLabel(label)).toBeVisible();
      }
      continue;
    }

    if ('assert_file_contains' in step) {
      const response = await page.request.get(`/api/fs/content?path=${encodeURIComponent(step.assert_file_contains.path)}`);
      expect(response.ok()).toBeTruthy();
      const body = (await response.json()) as { content: string };
      expect(body.content).toContain(step.assert_file_contains.text);
      continue;
    }
  }

  for (const assertion of scenario.asserts ?? []) {
    if ('visible' in assertion) {
      const { label, title, testId } = assertion.visible;
      if (testId) {
        await expect(page.getByTestId(testId)).toBeVisible();
      } else if (title) {
        await expect(page.getByTitle(title)).toBeVisible();
      } else if (label) {
        await expect(page.getByLabel(label)).toBeVisible();
      }
      continue;
    }

    if ('file_contains' in assertion) {
      const response = await page.request.get(`/api/fs/content?path=${encodeURIComponent(assertion.file_contains.path)}`);
      expect(response.ok()).toBeTruthy();
      const body = (await response.json()) as { content: string };
      expect(body.content).toContain(assertion.file_contains.text);
      continue;
    }

    if ('file_exists' in assertion) {
      const response = await page.request.get(`/api/fs/content?path=${encodeURIComponent(assertion.file_exists.path)}`);
      expect(response.ok()).toBeTruthy();
    }
  }
}

const scenarios = loadScenarios().filter((scenario) => scenario.status === 'active');

for (const scenario of scenarios) {
  test(scenario.id, async ({ page }) => {
    page.on('pageerror', (error) => {
      console.log(`[pageerror] ${error.message}`);
    });
    page.on('console', (message) => {
      if (message.type() === 'error') {
        console.log(`[console-error] ${message.text()}`);
      }
    });
    await runScenario(page, scenario);
  });
}
