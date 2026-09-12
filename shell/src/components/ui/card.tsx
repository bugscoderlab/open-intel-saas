import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn("rounded-lg border border-gray-200 bg-white p-5 shadow-sm", className)}
      {...props}
    />
  );
}

export function CardTitle({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h2 className={cn("mb-3 text-base font-semibold text-gray-900", className)}>
      {children}
    </h2>
  );
}
