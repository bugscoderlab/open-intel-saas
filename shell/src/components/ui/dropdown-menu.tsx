"use client";

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function DropdownMenu({ ...props }: ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root {...props} />;
}

export function DropdownMenuTrigger({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return (
    <DropdownMenuPrimitive.Trigger
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50 data-[state=open]:bg-gray-50",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuContent({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        sideOffset={4}
        className={cn(
          "z-50 min-w-48 rounded-md border border-gray-200 bg-white p-1 shadow-md",
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        "cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-gray-100",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-2 py-1 text-xs font-medium text-gray-500">{children}</div>
  );
}
