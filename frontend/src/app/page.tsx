"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type LogType = "info" | "success" | "error";
type RunStage = "idle" | "resolving" | "discovering" | "rendering" | "complete" | "error";

type RunState = {
  stage: RunStage;
  stageLabel: string;
  stageDescription: string;
  progress: number;
  discovered: number | null;
  saved: number;
  errors: number;
};

type LogEntry = {
  id: string;
  text: string;
  type: LogType;
};

const INITIAL_RUN_STATE: RunState = {
  stage: "idle",
  stageLabel: "Ready",
  stageDescription: "Enter a Medium profile or writer link and date range to begin.",
  progress: 0,
  discovered: null,
  saved: 0,
  errors: 0,
};

function toLocalInputDate(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function shiftDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function getInitialRange(): { start: string; end: string } {
  const today = new Date();
  const start = shiftDays(today, -6);
  return { start: toLocalInputDate(start), end: toLocalInputDate(today) };
}

function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDisplayDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parseLocalDate(value));
}

function formatMonthLabel(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
  }).format(date);
}

function addMonths(date: Date, amount: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

function startOfCalendarGrid(date: Date): Date {
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const day = first.getDay();
  const offset = day === 0 ? 6 : day - 1;
  return shiftDays(first, -offset);
}

function buildCalendarDays(viewMonth: Date): Date[] {
  const start = startOfCalendarGrid(viewMonth);
  return Array.from({ length: 42 }, (_, index) => shiftDays(start, index));
}

function isSameDay(left: Date, right: Date): boolean {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

type DatePickerProps = {
  label: string;
  value: string;
  onChange: (next: string) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
};

function DatePicker({ label, value, onChange, min, max, disabled = false }: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => {
    if (value) {
      const selected = parseLocalDate(value);
      return new Date(selected.getFullYear(), selected.getMonth(), 1);
    }
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const selectedDate = value ? parseLocalDate(value) : null;
  const minDate = min ? parseLocalDate(min) : null;
  const maxDate = max ? parseLocalDate(max) : null;
  const days = useMemo(() => buildCalendarDays(viewMonth), [viewMonth]);

  return (
    <div ref={rootRef} className="relative space-y-2">
      <Label className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/52">{label}</Label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (value) {
            const selected = parseLocalDate(value);
            setViewMonth(new Date(selected.getFullYear(), selected.getMonth(), 1));
          }
          setOpen((current) => !current);
        }}
        className="flex h-14 w-full items-center justify-between rounded-2xl border border-white/18 bg-white/6 px-4 text-left text-white transition-colors hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-45"
      >
        <span className="text-[15px]">{formatDisplayDate(value)}</span>
        <CalendarDays className="size-4 text-white/54" />
      </button>

      {open ? (
        <div className="absolute left-0 top-full z-30 mt-3 w-[20rem] rounded-[24px] border border-white/12 bg-black/90 p-4 shadow-[0_20px_80px_rgba(0,0,0,0.45)] backdrop-blur-2xl">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setViewMonth((current) => addMonths(current, -1))}
              className="flex size-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-white transition-colors hover:bg-white/[0.08]"
            >
              <ChevronLeft className="size-4" />
            </button>
            <div className="text-sm font-medium text-white">{formatMonthLabel(viewMonth)}</div>
            <button
              type="button"
              onClick={() => setViewMonth((current) => addMonths(current, 1))}
              className="flex size-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-white transition-colors hover:bg-white/[0.08]"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>

          <div className="mt-4 grid grid-cols-7 gap-1 text-center text-[10px] font-medium uppercase tracking-[0.18em] text-white/34">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
              <div key={day} className="py-2">
                {day}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {days.map((day) => {
              const isSelected = selectedDate ? isSameDay(day, selectedDate) : false;
              const isOutsideMonth = day.getMonth() !== viewMonth.getMonth();
              const tooEarly = minDate ? day < minDate : false;
              const tooLate = maxDate ? day > maxDate : false;
              const disabled = tooEarly || tooLate;

              return (
                <button
                  key={day.toISOString()}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    onChange(toLocalInputDate(day));
                    setOpen(false);
                  }}
                  className={cn(
                    "flex h-10 items-center justify-center rounded-xl text-sm transition-colors",
                    isSelected
                      ? "bg-white text-black"
                      : isOutsideMonth
                        ? "text-white/22"
                        : "text-white/78 hover:bg-white/[0.08]",
                    disabled && "cursor-not-allowed text-white/14 hover:bg-transparent"
                  )}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function prettyFileName(file: string): string {
  return file.replace(/\.pdf$/i, "").replace(/-/g, " ");
}

function extractMediumIdentifier(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;

  // Allow plain handles and raw writer IDs to continue working.
  if (!raw.includes("medium.com") && !/^https?:\/\//i.test(raw)) {
    const identifier = raw.replace(/^@/, "").replace(/\s+/g, "");
    return identifier || null;
  }

  const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

  try {
    const url = new URL(withProtocol);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");

    if (host === "medium.com") {
      const segments = url.pathname.split("/").filter(Boolean);
      if (segments[0]?.startsWith("@")) {
        const handle = segments[0].slice(1).trim();
        return handle || null;
      }

      if (
        segments[0] === "me" &&
        segments[1] === "following-feed" &&
        segments[2] === "writers" &&
        /^[a-f0-9]{12,}$/i.test(segments[3] ?? "")
      ) {
        return segments[3];
      }
    }

    if (host.endsWith(".medium.com")) {
      const subdomain = host.replace(/\.medium\.com$/, "").trim();
      return subdomain || null;
    }
  } catch {
    return null;
  }

  return null;
}

function classifyLogMessage(message: string, previous: RunState): Partial<RunState> {
  const next: Partial<RunState> = {};

  if (/^Account:/.test(message) || /^Date range:/.test(message) || /^Output dir:/.test(message)) {
    next.stage = "resolving";
    next.stageLabel = "Preparing";
    next.stageDescription = "Connecting the request to the scraper.";
    next.progress = Math.max(previous.progress, 10);
  }

  if (/Discovering posts via Medium API/i.test(message)) {
    next.stage = "discovering";
    next.stageLabel = "Scanning";
    next.stageDescription = "Trying the fastest discovery path first.";
    next.progress = Math.max(previous.progress, 28);
  }

  if (/Matched (\d+) article\(s\) in requested date range via API/i.test(message)) {
    const count = Number(message.match(/Matched (\d+) article/i)?.[1] ?? "0");
    next.discovered = count;
    next.stage = "discovering";
    next.stageLabel = count > 0 ? "Articles found" : "Looking for a fallback";
    next.stageDescription =
      count > 0
        ? "The API path found in-range articles."
        : "The API path returned no usable posts, so the scraper is trying other sources.";
    next.progress = Math.max(previous.progress, 36);
  }

  if (/API discovery returned 0 articles in the requested range/i.test(message)) {
    next.stage = "discovering";
    next.stageLabel = "Using fallback";
    next.stageDescription = "The primary path returned no usable posts for this range.";
    next.progress = Math.max(previous.progress, 44);
  }

  if (/Archive discovery found no candidate URLs/i.test(message)) {
    next.stage = "discovering";
    next.stageLabel = "Trying profile fallback";
    next.stageDescription = "Archive pages were blocked, so the profile page is being parsed instead.";
    next.progress = Math.max(previous.progress, 52);
  }

  if (/Found (\d+) article\(s\) in profile fallback/i.test(message)) {
    const count = Number(message.match(/Found (\d+) article/i)?.[1] ?? "0");
    next.discovered = count;
    next.stage = "rendering";
    next.stageLabel = "Extracting articles";
    next.stageDescription = "The article list is ready; files are being extracted.";
    next.progress = Math.max(previous.progress, 68);
  }

  if (/Inspecting article metadata:/i.test(message)) {
    next.stage = "rendering";
    next.stageLabel = "Validating";
    next.stageDescription = "Confirming publish dates before download.";
    next.progress = Math.max(previous.progress, 72);
  }

  if (/Saved full PDF:/i.test(message)) {
    next.stage = "rendering";
    next.stageLabel = "Saving";
    next.stageDescription = "An article was written to disk.";
    next.saved = previous.saved + 1;
    next.progress = Math.max(previous.progress, 88);
  }

  const successMatch = message.match(/Successfully saved (\d+)\/(\d+) articles/i);
  if (successMatch) {
    next.saved = Number(successMatch[1]);
    next.discovered = Number(successMatch[2]);
    next.stage = "complete";
    next.stageLabel = "Done";
    next.stageDescription = "All completed files are ready for download.";
    next.progress = 100;
  }

  if (/Processing complete\./i.test(message)) {
    next.stage = "complete";
    next.stageLabel = "Done";
    next.stageDescription = "The extraction run completed.";
    next.progress = 100;
  }

  if (/Critical Error/i.test(message) || /Connection error/i.test(message) || (/failed/i.test(message) && !/SSL verify failed/i.test(message))) {
    next.stage = "error";
    next.stageLabel = "Blocked";
    next.stageDescription = message;
    next.errors = previous.errors + 1;
    next.progress = Math.max(previous.progress, 100);
  }

  return next;
}

export default function Home() {
  const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001").replace(/\/$/, "");
  const initialRange = getInitialRange();

  const [profileInput, setProfileInput] = useState("");
  const [startDate, setStartDate] = useState(initialRange.start);
  const [endDate, setEndDate] = useState(initialRange.end);
  const [isProcessing, setIsProcessing] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [files, setFiles] = useState<string[]>([]);
  const [runState, setRunState] = useState<RunState>(INITIAL_RUN_STATE);

  const fetchFiles = useCallback(async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/api/files`);
      const data = await res.json();
      if (Array.isArray(data.files)) {
        setFiles(data.files);
      }
    } catch (error) {
      console.error("Failed to fetch files:", error);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleReset = () => {
    setIsProcessing(false);
    setLogs([]);
    setRunState(INITIAL_RUN_STATE);
  };

  const handleStart = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();

    const cleanUsername = extractMediumIdentifier(profileInput);

    if (!cleanUsername) {
      toast.error("Enter a valid Medium profile link, writer link, or handle.");
      return;
    }

    if (!startDate || !endDate) {
      toast.error("Choose both dates before starting.");
      return;
    }

    if (new Date(startDate) > new Date(endDate)) {
      toast.error("Start date must be on or before end date.");
      return;
    }

    const targetLabel = /^[a-f0-9]{12,}$/i.test(cleanUsername) ? cleanUsername : `@${cleanUsername}`;

    setIsProcessing(true);
    setFiles([]);
    setLogs([
      {
        id: Date.now().toString(),
        text: `Starting run for ${targetLabel} from ${startDate} to ${endDate}.`,
        type: "info",
      },
    ]);
    setRunState({
      ...INITIAL_RUN_STATE,
      stage: "resolving",
      stageLabel: "Preparing",
      stageDescription: "Connecting the request to the scraper.",
      progress: 10,
    });

    try {
      const response = await fetch(`${apiBaseUrl}/api/convert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: cleanUsername,
          start_date: startDate,
          end_date: endDate,
        }),
      });

      if (!response.body) {
        throw new Error("No response body.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let done = false;

      const processEvents = (chunk: string, isLast: boolean) => {
        buffer += chunk;
        const events = buffer.split(/\r?\n\r?\n/);
        
        if (!isLast) {
          buffer = events.pop() ?? "";
        } else {
          buffer = "";
        }

        for (const event of events) {
          if (!event.trim().startsWith("data: ")) continue;

          try {
            // "data: ".length === 6
            const data = JSON.parse(event.trim().substring(6));
            if (data.type === "log") {
              const message = String(data.message ?? "");
              const type: LogType = /Saved full PDF|Successfully saved/i.test(message)
                ? "success"
                : (/Error on|failed|skipping/i.test(message) && !/SSL verify failed/i.test(message))
                  ? "error"
                  : "info";

              setLogs((prev) => [...prev, { id: Math.random().toString(), text: message, type }]);
              setRunState((prev) => ({
                ...prev,
                ...classifyLogMessage(message, prev),
              }));
            }

            if (data.type === "done") {
              const status = Number(data.status ?? 0);
              setRunState((prev) => ({
                ...prev,
                stage: status === 0 ? "complete" : "error",
                stageLabel: status === 0 ? "Done" : "Blocked",
                stageDescription:
                  status === 0
                    ? "The articles are ready in the output area."
                    : "The run finished, but one or more steps reported an issue.",
                progress: 100,
              }));

              setLogs((prev) => [
                ...prev,
                {
                  id: "done",
                  text: status === 0 ? "Processing complete." : "Processing finished with errors.",
                  type: status === 0 ? "success" : "error",
                },
              ]);

              if (status === 0) {
                toast.success("Finished processing all articles.");
              } else {
                toast.error("Finished with some errors.");
              }
              fetchFiles();
            }

            if (data.type === "error") {
              const message = String(data.message ?? "Unknown error");
              setRunState((prev) => ({
                ...prev,
                stage: "error",
                stageLabel: "Blocked",
                stageDescription: message,
                progress: 100,
                errors: prev.errors + 1,
              }));
              setLogs((prev) => [
                ...prev,
                { id: Math.random().toString(), text: `Critical Error: ${message}`, type: "error" },
              ]);
              toast.error(message);
            }
          } catch {
            // Ignore partial SSE chunks.
          }
        }
      };

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;

        if (value) {
          processEvents(decoder.decode(value, { stream: !done }), done);
        } else if (done && buffer.length > 0) {
          processEvents("", true);
        }
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown error";
      toast.error(`Failed to connect to the backend: ${message}`);
      setLogs((prev) => [...prev, { id: "err", text: `Connection error: ${message}`, type: "error" }]);
      setRunState((prev) => ({
        ...prev,
        stage: "error",
        stageLabel: "Blocked",
        stageDescription: message,
        progress: 100,
        errors: prev.errors + 1,
      }));
    } finally {
      setIsProcessing(false);
      fetchFiles();
    }
  };

  const handleDownload = (filename: string) => {
    window.open(`${apiBaseUrl}/api/download/${encodeURIComponent(filename)}`, "_blank");
  };

  const handleDownloadAll = () => {
    window.open(`${apiBaseUrl}/api/download-all`, "_blank");
  };

  const isComplete = runState.stage === "complete";
  const savedCount = runState.saved > 0 ? runState.saved : files.length;

  const renderSetup = () => (
    <form className="mt-10 space-y-6" onSubmit={handleStart}>
      <div className="space-y-2">
        <Label htmlFor="username" className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/52">
          Medium profile
        </Label>
        <Input
          id="username"
          placeholder="@username"
          value={profileInput}
          onChange={(e) => setProfileInput(e.target.value)}
          disabled={isProcessing}
          className="h-16 rounded-full border-white/24 bg-white/[0.06] px-6 text-base text-white placeholder:text-white/30 focus-visible:ring-4 focus-visible:ring-white/15"
        />
        <p className="text-sm leading-6 text-white/58">
          Paste a Medium profile link, writer link, or handle.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <DatePicker label="Start date" value={startDate} onChange={setStartDate} max={endDate} disabled={isProcessing} />
        <DatePicker label="End date" value={endDate} onChange={setEndDate} min={startDate} disabled={isProcessing} />
      </div>

      <Button
        type="submit"
        disabled={isProcessing || !profileInput.trim() || !startDate || !endDate}
        className="h-14 rounded-full bg-white px-6 text-sm font-medium text-black hover:bg-[#e2e2e2] disabled:bg-white/16 disabled:text-white/34"
      >
        Start scraping
      </Button>
    </form>
  );

  const renderRunning = () => (
    <div className="mt-10 space-y-5">
      <div className="inline-flex items-center gap-3 rounded-full border border-white/14 bg-white/6 px-4 py-3 text-sm text-white">
        <Loader2 className="size-4 animate-spin" />
        <span>{runState.stageLabel}</span>
      </div>
      <p className="max-w-xl text-base leading-7 text-white/72">{runState.stageDescription}</p>
      <p className="text-sm leading-6 text-white/46">{runState.progress}% complete. Keep this tab open until the run finishes.</p>
    </div>
  );

  const renderComplete = () => (
    <div className="mt-10 space-y-6">
      <div className="space-y-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/52">Finished</p>
        <p className="max-w-xl text-base leading-7 text-white/76">
          {savedCount > 0
            ? `${savedCount} article${savedCount === 1 ? "" : "s"} ready for download.`
            : "The run completed, but no articles are visible yet."}
        </p>
      </div>

      {files.length > 0 ? (
        <div className="space-y-3">
          {files.map((file) => (
            <div
              key={file}
              className="flex flex-col gap-4 rounded-[22px] border border-white/12 bg-white/4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="truncate text-base font-medium text-white" title={prettyFileName(file)}>
                  {prettyFileName(file)}
                </div>
                <div className="truncate text-sm text-white/42">{file}</div>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleDownload(file)}
                className="rounded-full border border-white bg-white px-4 text-sm font-medium text-black hover:bg-[#e2e2e2]"
              >
                <Download className="mr-2 size-4" />
                Download
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm leading-6 text-white/46">
          Refresh if the backend just finished writing output.
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button
          type="button"
          onClick={handleDownloadAll}
          disabled={files.length === 0}
          className="rounded-full bg-white px-5 text-sm font-medium text-black hover:bg-[#e2e2e2] disabled:bg-white/16 disabled:text-white/34"
        >
          Download all as ZIP
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={handleReset}
          className="rounded-full border border-white/16 bg-transparent px-5 text-sm font-medium text-white hover:bg-white/8"
        >
          Start another export
        </Button>
      </div>
    </div>
  );

  const renderError = () => (
    <div className="mt-10 space-y-5">
      <div className="inline-flex items-center gap-3 rounded-full border border-white/14 bg-white/6 px-4 py-3 text-sm text-white">
        <AlertTriangle className="size-4" />
        <span>Run blocked</span>
      </div>
      <p className="max-w-xl text-base leading-7 text-white/72">{runState.stageDescription}</p>
      <Button
        type="button"
        variant="ghost"
        onClick={handleReset}
        className="rounded-full border border-white bg-white px-5 text-sm font-medium text-black hover:bg-[#e2e2e2]"
      >
        Back to input
      </Button>
    </div>
  );

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-black px-6 pb-40 pt-10 text-white sm:px-8 lg:px-12 lg:pb-64">
      <div className="openmedium-gradient-field pointer-events-none" aria-hidden="true">
        <div className="openmedium-gradient-layer openmedium-gradient-layer-a" />
        <div className="openmedium-gradient-layer openmedium-gradient-layer-b" />
        <div className="openmedium-gradient-layer openmedium-gradient-layer-c" />
        <div className="openmedium-gradient-layer openmedium-gradient-layer-d" />
        <div className="openmedium-gradient-layer openmedium-gradient-layer-e" />
        <div className="openmedium-gradient-noise" />
      </div>

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center">
        <div className="w-full max-w-3xl">
          <div className="openmedium-wordmark flex items-baseline gap-1 sm:gap-1.5" aria-label="OpenMedium">
            <span
              className="openmedium-wordmark-text block text-[42px] font-semibold leading-none tracking-[-0.055em] sm:text-[48px]"
              style={{ fontFamily: "var(--font-wordmark-stack)" }}
            >
              Open
            </span>
            <span
              className="openmedium-wordmark-text block text-[42px] font-semibold leading-none tracking-[-0.055em] sm:text-[48px]"
              style={{ fontFamily: "var(--font-wordmark-stack)" }}
            >
              Medium
            </span>
          </div>
          <h1 className="mt-6 max-w-2xl text-5xl font-semibold tracking-[-0.06em] text-white sm:text-6xl lg:text-7xl">
            Get every article from any Medium profile.
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-white/62">
            Select an author and a date range. We&apos;ll automatically scrape their posts, bypass the paywall, and package them as PDFs.
          </p>

          {isComplete ? renderComplete() : runState.stage === "error" ? renderError() : isProcessing ? renderRunning() : renderSetup()}

          {logs.length > 0 ? (
            <details className="mt-12 group">
              <summary className="flex cursor-pointer list-none items-center gap-3 text-[11px] font-medium uppercase tracking-[0.18em] text-white/42">
                <span>Technical details</span>
                <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
              </summary>
              <div className="mt-4 max-h-56 overflow-auto rounded-[20px] border border-white/10 bg-white/[0.04] p-4 font-mono text-xs text-white/76">
                <div className="space-y-2">
                  {logs.map((log) => (
                    <div
                      key={log.id}
                      className={cn(
                        "flex items-start gap-2",
                        log.type === "error"
                          ? "text-white"
                          : log.type === "success"
                            ? "text-white"
                            : "text-white/62"
                      )}
                    >
                      <span className="select-none opacity-40">&gt;</span>
                      <span className="break-words leading-relaxed">{log.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </main>
  );
}
