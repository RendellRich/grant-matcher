// CSV and calendar files, built in the browser and handed over as downloads.
import type { FederalExtra, FederalRec, Scored } from "./score";

type Cell = string | number | boolean | null | undefined;

function csvCell(v: Cell): string {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(header: string[], rows: Cell[][]): string {
  return [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

export function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const ymd = (d: Date) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;

/** One all-day event per deadline, as match.to_ics writes it. */
export function toIcs(rows: Scored<FederalRec & FederalExtra>[]): string {
  const stamp = ymd(new Date());
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//grant-matcher//EN", "CALSCALE:GREGORIAN"];
  for (const { rec: r } of rows) {
    if (!r.close) continue;
    const label = r.status === "forecasted" ? "Est. due" : "Due";
    const title = `${label}: ${r.title}`.replace(/[,;\\]/g, " ").slice(0, 150);
    lines.push("BEGIN:VEVENT", `UID:grant-${r.id}@grant-matcher`, `DTSTAMP:${stamp}T000000Z`,
      `DTSTART;VALUE=DATE:${ymd(r.close)}`, `SUMMARY:${title}`, `DESCRIPTION:${r.agency} ${r.number} ${r.url}`,
      `URL:${r.url}`, "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.join("\r\n") + "\r\n";
}
