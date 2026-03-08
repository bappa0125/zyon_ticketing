"use client";

import { useState, useEffect } from "react";
import { SocialTable, SocialPost } from "@/components/SocialTable";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

export default function SocialPage() {
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [entityFilter, setEntityFilter] = useState<string>("");

  useEffect(() => {
    async function fetchPosts() {
      try {
        const url = entityFilter
          ? `${getApiUrl()}/social/latest?entity=${encodeURIComponent(entityFilter)}`
          : `${getApiUrl()}/social/latest`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setPosts(data.posts ?? []);
      } catch (err) {
        console.error("fetchPosts failed:", err);
        setPosts([]);
      } finally {
        setLoading(false);
      }
    }
    fetchPosts();
  }, [entityFilter]);

  return (
    <div className="min-h-screen bg-[var(--background)] p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link
            href="/"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            ← Chat
          </Link>
          <Link
            href="/clients"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Clients
          </Link>
          <Link
            href="/media"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Media
          </Link>
          <Link
            href="/opportunities"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Opportunities
          </Link>
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Social Monitoring
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Latest social mentions (Twitter, YouTube). Filter by entity:
        </p>
        <input
          type="text"
          placeholder="Entity (e.g. Sahi)"
          value={entityFilter}
          onChange={(e) => setEntityFilter(e.target.value)}
          className="mb-4 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
        />
        <SocialTable posts={posts} loading={loading} />
      </div>
    </div>
  );
}
