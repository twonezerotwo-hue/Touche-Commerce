import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("is its own panel by default", () => {
    render(<EmptyState title="Nothing here" description="Add one." />);
    const root = screen.getByText("Nothing here").parentElement;
    expect(root).toHaveClass("panel");
    expect(root).not.toHaveAttribute("data-embedded");
  });

  it("drops the panel chrome when it already sits inside a panel", () => {
    render(
      <div className="panel">
        <EmptyState embedded title="No orders match" />
      </div>,
    );
    const root = screen.getByText("No orders match").parentElement;
    expect(root).not.toHaveClass("panel");
    expect(root).toHaveAttribute("data-embedded", "true");
    expect(document.querySelectorAll(".panel")).toHaveLength(1);
  });
});
