"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MapPreview } from "@/components/landing/MapPreview";
import { MasteryDemo } from "@/components/landing/MasteryDemo";
import { Reveal } from "@/components/Reveal";
import { api } from "@/lib/api";

const STEPS = [
  {
    n: "01",
    title: "Drop in your material",
    body: "PDFs (even scanned ones), slides, Word docs, web pages, YouTube lectures. Whatever your course runs on.",
  },
  {
    n: "02",
    title: "Get a map of the course",
    body: "Every topic, grouped into units, with arrows showing what you need to learn first. Built from your notes, not a generic syllabus.",
  },
  {
    n: "03",
    title: "Study what you don't know",
    body: "A ten-question diagnostic colours the map. From then on, every question goes where it moves you most.",
  },
];

const FEATURES = [
  { icon: "◉", title: "Mastery map", body: "See every topic coloured by how likely you are to know it. Click one to study it." },
  { icon: "?", title: "Adaptive practice", body: "Questions on your weakest topic whose prerequisites you've got, never the one you can't reach yet." },
  { icon: "❝", title: "Ask with citations", body: "Answers come only from your sources, with the page or timestamp, and start with what you're missing." },
  { icon: "✓", title: "Checked questions", body: "Each question cites its source and passes a second check. Numerical answers are verified by running the maths." },
  { icon: "↻", title: "Flashcards that time themselves", body: "Spaced repetition brings each card back just before you'd forget it." },
  { icon: "⌂", title: "Private by default", body: "Runs on your machine with a local model. Your notes never have to leave your laptop." },
];

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(() => setSignedIn(true))
      .catch(() => setSignedIn(false));
  }, []);

  const primary = signedIn ? { href: "/spaces", label: "Go to your spaces" } : { href: "/login", label: "Get started — it's free" };

  return (
    <div className="relative overflow-x-hidden">
      {/* Nav */}
      <header className="sticky top-0 z-30 border-b border-line/60 bg-surface/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" />
            Study Copilot
          </Link>
          <nav className="flex items-center gap-2 text-sm">
            <a href="#how" className="hidden px-3 py-2 text-ink-2 hover:text-ink sm:inline">
              How it works
            </a>
            <a href="#features" className="hidden px-3 py-2 text-ink-2 hover:text-ink sm:inline">
              Features
            </a>
            {signedIn ? (
              <Link href="/spaces" className="btn">
                Your spaces
              </Link>
            ) : (
              <>
                <Link href="/login" className="btn-ghost">
                  Sign in
                </Link>
                <Link href="/login" className="btn hidden sm:inline-flex">
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative">
        <div className="hero-glow pointer-events-none absolute inset-0 -z-10" />
        <div className="hero-grid pointer-events-none absolute inset-0 -z-10" />
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:py-24 lg:min-h-[min(calc(100svh-57px),860px)] lg:grid-cols-[1.1fr_1fr]">
          <div>
            <Reveal>
              <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 text-xs text-ink-2 backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-good" />
                Your notes, turned into a tutor that knows you
              </span>
            </Reveal>
            <Reveal delay={100}>
              <h1 className="mt-6 text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
                Study what you
                <br />
                <span className="text-gradient">don&apos;t know yet.</span>
              </h1>
            </Reveal>
            <Reveal delay={200}>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
                Upload your notes, slides and lectures. Study Copilot maps every topic, works out what you&apos;ve
                already mastered, and teaches the rest, starting from the prerequisites you&apos;re missing.
              </p>
            </Reveal>
            <Reveal delay={300}>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href={primary.href} className="btn px-5 py-3 text-base">
                  {primary.label}
                </Link>
                <a href="#how" className="btn-ghost px-5 py-3 text-base">
                  See how it works
                </a>
              </div>
            </Reveal>
          </div>
          <Reveal delay={250}>
            <MapPreview />
          </Reveal>
        </div>
        <a
          href="#tagline"
          className="scroll-hint absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center text-xs text-muted md:flex"
          aria-label="Scroll down"
        >
          <span>Scroll</span>
          <span className="text-lg leading-none">↓</span>
        </a>
      </section>

      {/* Tagline */}
      <section id="tagline" className="border-y border-line bg-surface-2/50">
        <div className="mx-auto max-w-4xl px-4 py-28 text-center">
          <Reveal>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-accent">The problem</p>
          </Reveal>
          <Reveal delay={100}>
            <h2 className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
              Chatbots explain the same way to everyone.
              <br />
              <span className="text-ink-2">This one keeps score.</span>
            </h2>
          </Reveal>
          <div className="mt-14 grid gap-6 text-left sm:grid-cols-3">
            {[
              ["Upload once.", "Your material becomes a map you can actually see."],
              ["Know where you stand.", "Every topic has a number: how likely you are to know it."],
              ["Spend time where it counts.", "No re-reading what you've got. No skipping what you need first."],
            ].map(([head, body], i) => (
              <Reveal key={head} delay={150 + i * 120}>
                <div className="h-full rounded-xl border border-line bg-surface p-5">
                  <div className="text-lg font-semibold">{head}</div>
                  <p className="mt-2 text-sm leading-relaxed text-ink-2">{body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-28">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-accent">How it works</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
            From a pile of PDFs to a plan, in a few minutes.
          </h2>
        </Reveal>
        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 140}>
              <div className="group relative h-full rounded-2xl border border-line bg-surface p-6 transition hover:-translate-y-1 hover:border-accent/60 hover:shadow-xl hover:shadow-black/5">
                <div className="font-mono text-sm text-accent">{s.n}</div>
                <h3 className="mt-3 text-xl font-semibold">{s.title}</h3>
                <p className="mt-2 leading-relaxed text-ink-2">{s.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Every answer counts */}
      <section className="border-y border-line bg-surface-2/50">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-28 lg:grid-cols-2">
          <Reveal>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-accent">Learns as you do</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Every answer moves the map.</h2>
            <p className="mt-4 max-w-lg text-lg leading-relaxed text-ink-2">
              Get a question right and your mastery goes up, along with the topics it builds on. Get one wrong and
              it knows which foundations to shore up next. No streaks, no guesswork, just a running estimate of what
              you know.
            </p>
          </Reveal>
          <Reveal delay={150}>
            <MasteryDemo />
          </Reveal>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-28">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-accent">Features</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
            Everything a good tutor does. Built from your own notes.
          </h2>
        </Reveal>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 120}>
              <div className="h-full rounded-2xl border border-line bg-surface p-6 transition hover:border-accent/60">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-lg text-accent">
                  {f.icon}
                </div>
                <h3 className="mt-4 font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{f.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Closing CTA */}
      <section className="relative overflow-hidden border-t border-line">
        <div className="hero-glow pointer-events-none absolute inset-0 -z-10 opacity-70" />
        <div className="mx-auto max-w-3xl px-4 py-28 text-center">
          <Reveal>
            <h2 className="text-4xl font-semibold tracking-tight sm:text-5xl">
              Your exam is coming.
              <br />
              <span className="text-gradient">Know exactly what to study.</span>
            </h2>
          </Reveal>
          <Reveal delay={150}>
            <p className="mx-auto mt-5 max-w-xl text-lg text-ink-2">
              Create a space, add your notes, and take the diagnostic. You&apos;ll see your map in minutes.
            </p>
          </Reveal>
          <Reveal delay={250}>
            <Link href={primary.href} className="btn mt-8 px-6 py-3 text-base">
              {primary.label}
            </Link>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-sm text-muted">
          <span>Study Copilot</span>
          <span>Runs locally. Your notes stay yours.</span>
        </div>
      </footer>
    </div>
  );
}
