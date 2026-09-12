"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import type { Member } from "@/lib/api/types";

/** Organization member list with roles (ticket #19). */
export function MembersPanel({
  members,
  currentUserId,
}: {
  members: Member[];
  currentUserId: string;
}) {
  return (
    <Card>
      <CardTitle>Members</CardTitle>
      <ul className="divide-y divide-gray-100">
        {members.map((member) => (
          <li
            key={member.app_user_id}
            className="flex items-center justify-between py-2"
          >
            <span className="text-sm text-gray-900">
              {member.email ?? member.app_user_id}
              {member.app_user_id === currentUserId ? " (you)" : ""}
            </span>
            <Badge tone={member.role === "member" ? "gray" : "blue"}>
              {member.role}
            </Badge>
          </li>
        ))}
        {members.length === 0 ? (
          <li className="py-2 text-sm text-gray-500">No members yet.</li>
        ) : null}
      </ul>
    </Card>
  );
}
