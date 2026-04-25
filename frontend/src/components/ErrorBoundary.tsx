import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  label?: string;
  fallback?: (args: { error: Error; reset: () => void }) => ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary${this.props.label ? `:${this.props.label}` : ""}]`, error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) {
      return this.props.fallback({ error, reset: this.reset });
    }
    return (
      <div className="pointer-events-auto w-full rounded border border-accent-iuu/40 bg-accent-iuu/10 p-3 text-[11px] text-accent-iuu">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle size={12} />
            {this.props.label ? `${this.props.label} crashed` : "Panel crashed"}
          </span>
          <button
            onClick={this.reset}
            className="flex items-center gap-1 rounded bg-accent-iuu/20 px-1.5 py-0.5 text-[10px] hover:bg-accent-iuu/30"
          >
            <RotateCcw size={10} />
            reset
          </button>
        </div>
        <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-snug">
          {error.message || String(error)}
        </pre>
      </div>
    );
  }
}
