import { Component, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props { children: ReactNode; fallback?: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error): State { return { hasError: true, error }; }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <AlertTriangle className="text-red-400" size={32} />
          <h2 className="text-sm font-semibold text-red-700">Xəta baş verdi</h2>
          <p className="text-xs text-red-600">{this.state.error?.message ?? 'Naməlum xəta'}</p>
          <button className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100" onClick={() => this.setState({ hasError: false, error: null })} type="button">
            Yenidən cəhd et
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
