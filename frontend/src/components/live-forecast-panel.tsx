"use client";

import { useRef, useState } from "react";
import { FileSpreadsheet, Sparkles, UploadCloud } from "lucide-react";

import { PaperAirplane } from "@/components/paper-airplane";
import { ProcessingMicrocopy } from "@/components/processing-microcopy";
import { Reveal } from "@/components/reveal";
import { ResultDisplay } from "@/components/result-display";
import { ApiError, runForecast } from "@/lib/api";
import { CsvFormatError, csvToTransactionRecords } from "@/lib/csv";
import type { ForecastOutput, TransactionRecord } from "@/lib/types";

const SAMPLE_THRESHOLD = 6_000_000;

export function LiveForecastPanel() {
  const [transactions, setTransactions] = useState<TransactionRecord[] | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<number>(0);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForecastOutput | null>(null);
  const [resultThreshold, setResultThreshold] = useState<number>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadFile(file: File) {
    setError(null);
    setResult(null);
    try {
      const text = await file.text();
      const records = csvToTransactionRecords(text);
      setTransactions(records);
      setFileName(file.name);
    } catch (err) {
      setTransactions(null);
      setFileName(null);
      setError(err instanceof CsvFormatError ? err.message : "Couldn't read that file as a ledger CSV.");
    }
  }

  async function loadSample() {
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/sample-ledger.csv");
      const text = await response.text();
      setTransactions(csvToTransactionRecords(text));
      setFileName("sample-ledger.csv");
      setThreshold(SAMPLE_THRESHOLD);
    } catch {
      setError("Couldn't load the sample ledger. Try uploading your own CSV instead.");
    }
  }

  async function handleRun() {
    if (!transactions) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const output = await runForecast(transactions, threshold);
      setResult(output);
      setResultThreshold(threshold);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The forecast request failed. Is the API running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="forecast" className="relative px-6 py-28">
      <PaperAirplane size={56} rotate={9} flip className="absolute top-14" bobDelay={0.6} />
      <div className="mx-auto max-w-5xl">
        <Reveal>
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-ember">
            Try it on real numbers
          </p>
          <h2 className="font-display text-4xl leading-tight text-ink sm:text-5xl">
            Bring your own ledger.
          </h2>
          <p className="mt-4 max-w-xl text-lg text-ink-muted">
            Upload a transaction history CSV, set the cash floor you care about,
            and runway will forecast the next fourteen days against it.
          </p>
        </Reveal>

        <Reveal delay={0.12} className="mt-12 max-w-3xl rounded-3xl border border-line bg-paper-card p-8 shadow-[0_1px_0_theme(colors.line)] sm:p-10">
          {/* Upload zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const file = e.dataTransfer.files?.[0];
              if (file) loadFile(file);
            }}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            className={`flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragging ? "border-ember bg-ember-dim" : "border-line hover:border-ink-faint"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) loadFile(file);
              }}
            />
            {fileName ? (
              <>
                <FileSpreadsheet className="size-7 text-ember" strokeWidth={1.5} />
                <p className="font-medium text-ink">{fileName}</p>
                <p className="text-sm text-ink-muted">
                  {transactions?.length ?? 0} transactions loaded — click to replace
                </p>
              </>
            ) : (
              <>
                <UploadCloud className="size-7 text-ink-faint" strokeWidth={1.5} />
                <p className="font-medium text-ink">Drop a ledger CSV here, or click to browse</p>
                <p className="text-sm text-ink-muted">date, type, category, amount, invoice_date, note</p>
              </>
            )}
          </div>

          <button
            type="button"
            onClick={loadSample}
            className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-moss transition-colors hover:text-ink"
          >
            <Sparkles className="size-3.5" />
            Don&rsquo;t have one handy? Use the sample ledger
          </button>

          {/* Threshold + run */}
          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-end">
            <label className="flex-1">
              <span className="mb-1.5 block text-sm font-medium text-ink">Shortfall threshold</span>
              <div className="flex items-center rounded-xl border border-line bg-paper px-4 py-3">
                <span className="mr-1 text-ink-faint">$</span>
                <input
                  type="number"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  className="w-full bg-transparent text-ink outline-none"
                  placeholder="0"
                />
              </div>
            </label>

            <button
              type="button"
              disabled={!transactions || loading}
              onClick={handleRun}
              className="rounded-xl bg-ember px-7 py-3.5 font-medium text-paper transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
            >
              {loading ? "Running…" : "Run forecast"}
            </button>
          </div>

          {/* Reserve space for status/result so nothing shifts around it */}
          <div className="mt-6 min-h-6">
            {error && <p className="text-sm text-ember">{error}</p>}
            <ProcessingMicrocopy active={loading} />
          </div>
        </Reveal>

        {result && !loading && <ResultDisplay result={result} threshold={resultThreshold} />}
      </div>
    </section>
  );
}
