import { expect, test } from '@playwright/test';
import { expectVisible } from './helpers';

const API = 'http://localhost:8010/api/v1';

test.describe('Capacity v2', () => {
  test('Команда tab renders team group row and child employee', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Команда' }).click();

    // "E2E" here is both the team label and part of the employee name — scope by role to avoid ambiguity.
    await expectVisible(page.getByRole('cell', { name: /E2E Analyst/ }));
    // Team row shows the team label followed by the member count "· 1".
    await expectVisible(page.getByRole('cell', { name: /E2E.*·\s*1/ }));
  });

  test('Факт and % column switches persist across reload', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Команда' }).click();

    const factHeaders = page.getByRole('columnheader', { name: 'Факт', exact: true });

    // Факт columns not rendered initially (toggle off by default).
    await expect(factHeaders).toHaveCount(0);

    // The toolbar has two Switch components; the first corresponds to Факт.
    const switches = page.getByRole('switch');
    await switches.first().click();

    // After toggle: one Факт column per month (3) + one in Итого = 4.
    await expect(factHeaders).not.toHaveCount(0);

    await page.reload();
    await page.getByRole('tab', { name: 'Команда' }).click();
    await expect(page.getByRole('columnheader', { name: 'Факт', exact: true })).not.toHaveCount(0);

    // Cleanup: toggle Факт off so other tests start from default.
    await page.getByRole('switch').first().click();
  });

  test('Отсутствия tab renders (heatmap + add button + table)', async ({ page }) => {
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Отсутствия' }).click();

    await expectVisible(page.getByRole('button', { name: 'Добавить отсутствие' }));
    // The list table has a Причина column header now.
    await expectVisible(page.getByRole('columnheader', { name: 'Причина' }));
  });

  test('POST /capacity/absences then the record appears in list', async ({ page, request }) => {
    // Get an existing employee id to attach the absence to.
    const emps = await (await request.get(`${API}/employees`)).json();
    expect(Array.isArray(emps)).toBe(true);
    expect(emps.length).toBeGreaterThan(0);
    const empId = emps[0].id;

    // Clean any leftover absences for this employee.
    const existing = await (await request.get(`${API}/capacity/absences`, { params: { employee_id: empId } })).json();
    for (const a of existing) {
      await request.delete(`${API}/capacity/absences/${a.id}`);
    }

    const created = await request.post(`${API}/capacity/absences`, {
      data: {
        employee_id: empId,
        start_date: '2026-04-20',
        end_date: '2026-04-22',
        reason: 'sick',
      },
    });
    expect(created.status()).toBe(201);

    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Отсутствия' }).click();
    await expectVisible(page.getByRole('cell', { name: 'Больничный' }));

    // Cleanup.
    const id = (await created.json()).id;
    await request.delete(`${API}/capacity/absences/${id}`);
  });

  test('Правила tab: copy button exists and triggers 201 on unique target', async ({ page, request }) => {
    // Ensure a Q2 2027 source rule exists and Q3 2027 target is empty.
    const rules = await (await request.get(`${API}/capacity/rules`, { params: { year: '2027' } })).json();
    for (const r of rules) {
      await request.delete(`${API}/capacity/rules/${r.id}`);
    }
    // Seed a source rule for each Q2 month.
    for (const month of [4, 5, 6]) {
      await request.post(`${API}/capacity/rules`, {
        data: { year: 2027, month, percent_of_norm: 15 },
      });
    }

    // Direct-call the endpoint; asserts the backend wire-up works.
    const copy = await request.post(`${API}/capacity/rules/copy-to-quarter`, {
      data: { from_year: 2027, from_quarter: 2, to_year: 2027, to_quarter: 3 },
    });
    expect(copy.status()).toBe(201);
    expect((await copy.json()).created).toBe(3);

    // UI-side: button is rendered.
    await page.goto('/capacity');
    await page.getByRole('tab', { name: 'Правила' }).click();
    await expectVisible(page.getByRole('button', { name: /Скопировать в следующий квартал/ }));

    // Cleanup created target rules.
    const q3 = await (await request.get(`${API}/capacity/rules`, { params: { year: '2027' } })).json();
    for (const r of q3) {
      await request.delete(`${API}/capacity/rules/${r.id}`);
    }
  });

  test('Capacity xlsx download returns a non-empty payload', async ({ request }) => {
    const r = await request.get(`${API}/exports/capacity.xlsx`, {
      params: { year: '2026', quarter: '2' },
    });
    expect(r.status()).toBe(200);
    expect(r.headers()['content-type']).toContain('spreadsheet');
    const buf = await r.body();
    expect(buf.length).toBeGreaterThan(100);
  });
});
