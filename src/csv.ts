/** Parse CSV records, including quoted commas/newlines and doubled quotes. */
export function parseCsv(text: string, maxRows = Infinity): string[][] {
  const rows: string[][] = []; let row: string[] = [], field = '', quoted = false, endedQuote = false;
  const input = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (quoted) {
      if (c === '"' && input[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; endedQuote = true; }
      else field += c;
    } else if (c === '"' && !field && !endedQuote) quoted = true;
    else if (c === ',' || c === '\n' || c === '\r') {
      row.push(field); field = ''; endedQuote = false;
      if (c !== ',') {
        rows.push(row); row = [];
        if (rows.length >= maxRows) return rows;
        if (c === '\r' && input[i + 1] === '\n') i++;
      }
    } else {
      if (endedQuote || c === '"') throw new Error('Invalid quoted CSV field');
      field += c;
    }
  }
  if (quoted) throw new Error('Unclosed quoted CSV field');
  if (row.length || field || endedQuote) { row.push(field); rows.push(row); }
  return rows;
}

export function encodeCsv(rows: (string | number | null | undefined)[][]): string {
  return rows.map(row => row.map(value => {
    const text = String(value ?? '');
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }).join(',')).join('\r\n') + '\r\n';
}
