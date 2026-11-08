import { Component, type ReactNode } from 'react'
import { Button, ErrorNote } from './ui'

/** A page that throws while rendering shows what went wrong and a way out, never a blank window (owner bug
 *  2026-11-08: a piece without narration crashed the project page and left it empty). Keyed per page by App, so
 *  moving to another page starts clean. */
export class PageBoundary extends Component<{ onHome: () => void; children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {}

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error('page crashed:', error)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <ErrorNote
        error={{ message: 'This page ran into a problem and could not be shown.', detail: this.state.error.message }}
        action={<Button onClick={this.props.onHome}>Go to the Dashboard</Button>}
      />
    )
  }
}
