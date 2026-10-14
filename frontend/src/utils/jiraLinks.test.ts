import { describe, expect, it } from 'vitest';
import { jiraBrowseUrl } from './jiraLinks';

describe('jiraBrowseUrl', () => {
  it('строит ссылку от адреса из настроек', () => {
    expect(jiraBrowseUrl('https://jira.example.test', 'OS-1')).toBe('https://jira.example.test/browse/OS-1');
    expect(jiraBrowseUrl('https://jira.example.test/', 'OS-1')).toBe('https://jira.example.test/browse/OS-1');
  });

  it('без адреса или ключа ссылки нет', () => {
    expect(jiraBrowseUrl(null, 'OS-1')).toBeNull();
    expect(jiraBrowseUrl('', 'OS-1')).toBeNull();
    expect(jiraBrowseUrl('https://jira.example.test', null)).toBeNull();
  });
});
