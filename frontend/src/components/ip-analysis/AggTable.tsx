import { ui } from '../../lib/ui';

type AggTableProps = {
  title: string;
  count: number;
  headers: string[];
  rows: string[][];
};

export function AggTable({ title, count, headers, rows }: AggTableProps) {
  if (!rows.length) return null;
  return (
    <div className={ui.panel}>
      <div className="flex items-center justify-between">
        <div className={ui.panelTitle}>{title}</div>
        <span className="text-xs text-gray-400">{count} nəticə</span>
      </div>
      <div className="mt-2 max-h-[300px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white">
            <tr className="border-b border-gray-200 text-left text-[11px] font-semibold uppercase text-gray-400">
              {headers.map((h) => <th className="px-3 py-1.5" key={h}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr className="border-b border-gray-50 hover:bg-gray-50" key={i}>
                {row.map((cell, j) => <td className="px-3 py-1.5 text-xs text-gray-700" key={j}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
