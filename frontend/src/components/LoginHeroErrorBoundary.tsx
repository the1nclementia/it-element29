import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { children: ReactNode; onFallback: () => void };
type State = { failed: boolean };

export class LoginHeroErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    this.props.onFallback();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}
