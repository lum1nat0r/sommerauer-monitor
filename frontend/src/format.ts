export function formatDate(value: string | Date, timeZone: string, options: Intl.DateTimeFormatOptions = {}) {
  try {
    return new Intl.DateTimeFormat('de-AT', {
      timeZone, dateStyle: 'medium', timeStyle: 'short', ...options,
    }).format(new Date(value));
  } catch {
    return 'Unbekannt';
  }
}

export function ageLabel(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'Alter unbekannt';
  if (seconds < 60) return `vor ${Math.floor(seconds)} s`;
  if (seconds < 3600) return `vor ${Math.floor(seconds / 60)} min`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `vor ${hours} h ${minutes} min`;
}
