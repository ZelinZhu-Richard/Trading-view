import { describe, expect, it } from 'vitest';
import { encodeCsv, parseCsv } from './csv';
describe('watchlist CSV boundaries', () => {
  it('preserves quoted commas, line breaks, quotes and Unicode', () => {
    const rows = [['instrument_id', 'section'], ['CSV:A', 'China, daily'], ['CSV:B', 'Line 1\nLine "2"'], ['CSV:C', '上海']];
    expect(parseCsv(encodeCsv(rows))).toEqual(rows);
  });
  it('handles BOM, CRLF, empty fields and limited header reads', () => {
    expect(parseCsv('\uFEFFa,b\r\n1,\r\n')).toEqual([['a', 'b'], ['1', '']]);
    expect(parseCsv('"a,b",c\n1,2', 1)).toEqual([['a,b', 'c']]);
  });
  it('rejects malformed quoting instead of shifting instrument identity', () => {
    expect(() => parseCsv('a,"unfinished')).toThrow('Unclosed');
    expect(() => parseCsv('"a"extra,b')).toThrow('Invalid');
  });
});
