"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";
import { TopicArticlesSection } from "@/components/PRIntelligence/TopicArticlesSection";
import { FirstMentionsSection } from "@/components/PRIntelligence/FirstMentionsSection";
import { AmplifiersSection } from "@/components/PRIntelligence/AmplifiersSection";
import { JournalistOutletsSection } from "@/components/PRIntelligence/JournalistOutletsSection";

type TabId = "topics" | "first-mentions" | "amplifiers" | "journalists";

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const;

export default function PRIntelligencePage() {
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [client, setClient] = useState("");
  const [range, setRange] = useState("7d");
  const [tab, setTab] = useState<TabId>("topics");
  const [topicFilter, setTopicFilter] = useState("");
  const [amplifierTopic, setAmplifierTopic] = useState("");

  const [topicArticles, setTopicArticles] = useState<unknown>(null);
  const [firstMentions, setFirstMentions] = useState<unknown>(null);
  const [amplifiers, setAmplifiers] = useState<unknown>(null);
  const [journalists, setJournalists] = useState<unknown>(null);

  const [loadingTopics, setLoadingTopics] = useState(false);
  const [loadingFirst, setLoadingFirst] = useState(false);
  const [loadingAmp, setLoadingAmp] = useState(false);
  const [loadingJournalists, setLoadingJournalists] = useState(false);

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) return;
        const json = await res.json();
        const list = json.clients ?? [];
        setClients(list);
        if (list.length > 0 && !client) setClient(list[0].name);
      } catch {
        setClients([]);
      }
    }
    fetchClients();
  }, []);

  const fetchTopicArticles = useCallback(async () => {
    if (!client.trim()) return;
    setLoadingTopics(true);
    try {
      const params = new URLSearchParams({ client, range });
      if (topicFilter.trim()) params.set("topic", topicFilter.trim());
      const res = await fetch(`${getApiBase()}/pr-intelligence/topic-articles?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTopicArticles(data);
    } catch (e) {
      console.error(e);
      setTopicArticles(null);
    } finally {
      setLoadingTopics(false);
    }
  }, [client, range, topicFilter]);

  const fetchFirstMentions = useCallback(async () => {
    if (!client.trim()) return;
    setLoadingFirst(true);
    try {
      const params = new URLSearchParams({ client, range });
      if (topicFilter.trim()) params.set("topic", topicFilter.trim());
      const res = await fetch(`${getApiBase()}/pr-intelligence/first-mentions?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setFirstMentions(data);
    } catch (e) {
      console.error(e);
      setFirstMentions(null);
    } finally {
      setLoadingFirst(false);
    }
  }, [client, range, topicFilter]);

  const fetchAmplifiers = useCallback(async () => {
    if (!client.trim() || !amplifierTopic.trim()) {
      setAmplifiers(null);
      return;
    }
    setLoadingAmp(true);
    try {
      const params = new URLSearchParams({ client, topic: amplifierTopic, range });
      const res = await fetch(`${getApiBase()}/pr-intelligence/amplifiers?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAmplifiers(data);
    } catch (e) {
      console.error(e);
      setAmplifiers(null);
    } finally {
      setLoadingAmp(false);
    }
  }, [client, range, amplifierTopic]);

  const fetchJournalists = useCallback(async () => {
    if (!client.trim()) return;
    setLoadingJournalists(true);
    try {
      const params = new URLSearchParams({ client, range });
      const res = await fetch(`${getApiBase()}/pr-intelligence/journalist-outlets?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setJournalists(data);
    } catch (e) {
      console.error(e);
      setJournalists(null);
    } finally {
      setLoadingJournalists(false);
    }
  }, [client, range]);

  useEffect(() => {
    if (tab === "topics") fetchTopicArticles();
  }, [tab, fetchTopicArticles]);

  useEffect(() => {
    if (tab === "first-mentions") fetchFirstMentions();
  }, [tab, fetchFirstMentions]);

  useEffect(() => {
    if (tab === "amplifiers" && amplifierTopic.trim()) fetchAmplifiers();
    else if (tab === "amplifiers" && !amplifierTopic.trim()) setAmplifiers(null);
  }, [tab, amplifierTopic, fetchAmplifiers]);

  useEffect(() => {
    if (tab === "journalists") fetchJournalists();
  }, [tab, fetchJournalists]);

  const tabs: { id: TabId; label: string }[] = [
    { id: "topics", label: "Topic–Article Mapping" },
    { id: "first-mentions", label: "First Mentions" },
    { id: "amplifiers", label: "Amplifiers" },
    { id: "journalists", label: "Journalist–Outlets" },
  ];

  const topicsList = (topicArticles as { topics?: { topic: string }[] })?.topics ?? [];

  return (
    <div className="app-page">
      <div className="max-w-6xl mx-auto p-6">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-[var(--ai-text)]">PR Intelligence</h1>
          <p className="text-sm text-[var(--ai-muted)] mt-1">
            Topic-article mapping, first mention detection, amplifier analysis, and journalist–outlet index.
          </p>
        </header>

        <section className="flex flex-wrap items-center gap-4 mb-6 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]">
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--ai-muted)]">Client</label>
            <select
              value={client}
              onChange={(e) => setClient(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)] min-w-[160px]"
            >
              <option value="">Select client</option>
              {clients.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--ai-muted)]">Period</label>
            <div className="flex rounded-lg overflow-hidden border border-[var(--ai-border)]">
              {RANGE_OPTIONS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRange(r.value)}
                  className={`px-3 py-2 text-sm transition-colors ${
                    range === r.value ? "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]" : "bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface-hover)]"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          {(tab === "topics" || tab === "first-mentions") && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-[var(--ai-muted)]">Topic filter</label>
              <input
                type="text"
                value={topicFilter}
                onChange={(e) => setTopicFilter(e.target.value)}
                placeholder="Filter topics"
                className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)] placeholder-[var(--ai-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)] w-48"
              />
            </div>
          )}
          {tab === "amplifiers" && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-[var(--ai-muted)]">Topic</label>
              <input
                type="text"
                list="topic-list"
                value={amplifierTopic}
                onChange={(e) => setAmplifierTopic(e.target.value)}
                placeholder="Enter topic for amplifier analysis"
                className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)] placeholder-[var(--ai-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)] min-w-[220px]"
              />
              <datalist id="topic-list">
                {topicsList.map((t) => (
                  <option key={t.topic} value={t.topic} />
                ))}
              </datalist>
              <button
                type="button"
                onClick={() => fetchAmplifiers()}
                disabled={!amplifierTopic.trim()}
                className="px-4 py-2 rounded-lg bg-[var(--ai-accent)] text-[var(--ai-bg)] font-medium text-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Analyze
              </button>
            </div>
          )}
        </section>

        <div className="flex gap-2 mb-6 border-b border-[var(--ai-border)] overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                tab === t.id
                  ? "border-[var(--ai-accent)] text-[var(--ai-accent)]"
                  : "border-transparent text-[var(--ai-text-secondary)] hover:text-[var(--ai-text)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {!client.trim() && (
          <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
            Select a client to view PR intelligence.
          </div>
        )}

        {client.trim() && (
          <>
            {tab === "topics" && <TopicArticlesSection data={topicArticles} loading={loadingTopics} />}
            {tab === "first-mentions" && <FirstMentionsSection data={firstMentions} loading={loadingFirst} />}
            {tab === "amplifiers" && <AmplifiersSection data={amplifiers} loading={loadingAmp} />}
            {tab === "journalists" && <JournalistOutletsSection data={journalists} loading={loadingJournalists} />}
          </>
        )}
      </div>
    </div>
  );
}
