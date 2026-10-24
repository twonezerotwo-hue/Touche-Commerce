import * as React from "react";

import { cn } from "@/lib/utils";

function Table({
  className,
  bare = false,
  ...props
}: React.ComponentProps<"table"> & { bare?: boolean }) {
  return (
    <div className={bare ? "overflow-hidden" : "panel overflow-hidden"}>
      {/* `relative` makes the scroller the containing block of absolutely positioned cells (the
          visually hidden header text); without it WebKit lets them widen the whole page on a phone. */}
      <div className="relative overflow-x-auto">
        <table
          data-slot="table"
          className={cn("w-full border-collapse text-left text-[12.5px]", className)}
          {...props}
        />
      </div>
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("border-b border-white/[0.07] bg-white/[0.018]", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("divide-y divide-white/[0.045]", className)}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn("group transition-colors duration-150 hover:bg-accent-400/[0.035]", className)}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      scope="col"
      className={cn(
        "whitespace-nowrap px-4 py-2.5 text-[9.5px] font-medium uppercase tracking-[0.16em] text-mist-500",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn("px-4 py-3.5 align-middle text-mist-300", className)}
      {...props}
    />
  );
}

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow };
