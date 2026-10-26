/** Shell + routing. The backend is the source of truth for every figure on screen. */

import { useMeta } from "@/api/queries";
import { Layout } from "@/components/Layout";
import { ErrorState } from "@/components/ui";
import { Accuracy } from "@/pages/Accuracy";
import { DecisionDesk } from "@/pages/DecisionDesk";
import { Method } from "@/pages/Method";
import { Procurement } from "@/pages/Procurement";
import { AppProvider, useApp } from "@/state/app";

function Screen() {
  const { route } = useApp();
  if (route === "accuracy") return <Accuracy />;
  if (route === "procurement") return <Procurement />;
  if (route === "method") return <Method />;
  return <DecisionDesk />;
}

export function App() {
  const meta = useMeta();

  if (meta.isLoading) {
    return (
      <div className="boot">
        <div className="boot__mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
        <p className="boot__text">Loading the forecast desk…</p>
      </div>
    );
  }

  if (meta.isError || !meta.data) {
    return (
      <div className="boot">
        <div className="boot__panel">
          <h1 className="boot__title">The API is not reachable</h1>
          <p className="boot__text">
            Start the FastAPI service (see the README for the exact command), then reload. In
            development Vite proxies <code>/api</code> to it. If it is already running, wait a moment
            for startup to finish.
          </p>
          <ErrorState error={meta.error ?? new Error("No metadata returned")} onRetry={() => meta.refetch()} />
        </div>
      </div>
    );
  }

  return (
    <AppProvider meta={meta.data}>
      <Layout>
        <Screen />
      </Layout>
    </AppProvider>
  );
}
