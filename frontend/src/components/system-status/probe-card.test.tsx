import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProbeCard } from "./probe-card";

describe("ProbeCard", () => {
  it("renders an operational probe with its rows and footer", () => {
    render(
      <ProbeCard
        eyebrow="Liveness"
        title="FastAPI service"
        state="operational"
        value="touche-commerce-api v0.1.0 answered HTTP 200."
        rows={[
          { label: "Endpoint", value: "/api/v1/health/live" },
          { label: "Request ID", value: "req-abc", mono: true },
        ]}
        footer="Liveness never touches PostgreSQL."
      />,
    );

    expect(screen.getByText("Operational")).toBeInTheDocument();
    expect(screen.getByText("FastAPI service")).toBeInTheDocument();
    expect(screen.getByText("touche-commerce-api v0.1.0 answered HTTP 200.")).toBeInTheDocument();
    expect(screen.getByText("/api/v1/health/live")).toBeInTheDocument();
    expect(screen.getByText("req-abc")).toBeInTheDocument();
    expect(screen.getByText("Liveness never touches PostgreSQL.")).toBeInTheDocument();
  });

  it("renders degraded and unreachable states explicitly", () => {
    const { container, rerender } = render(
      <ProbeCard
        eyebrow="Readiness"
        title="PostgreSQL"
        state="degraded"
        value="connection timeout expired"
        rows={[{ label: "Server", value: "not reported" }]}
      />,
    );

    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(container.querySelector('[data-probe-state="degraded"]')).not.toBeNull();
    expect(screen.queryByText(/Error code/)).toBeNull();

    rerender(
      <ProbeCard
        eyebrow="Liveness"
        title="FastAPI service"
        state="unreachable"
        value="Cannot reach the API."
        rows={[]}
      />,
    );

    expect(screen.getByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Cannot reach the API.")).toBeInTheDocument();
  });
});
