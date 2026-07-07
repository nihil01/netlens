import { Loader2 } from 'lucide-react';
import { cn, ui } from '../lib/ui';

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div className={cn(ui.panel, 'flex items-center gap-2 text-sm text-blue-600')}>
      <Loader2 className="animate-spin" size={16} />
      {label}
    </div>
  );
}
