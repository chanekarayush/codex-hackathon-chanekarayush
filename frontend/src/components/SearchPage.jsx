import { ArrowUp, BookOpen, Loader2, Mic, Search, Video } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import BookResultCard from "./BookResultCard.jsx";
import MotivationRail from "./MotivationRail.jsx";
import RelatedQuestions from "./RelatedQuestions.jsx";
import ResultCard from "./ResultCard.jsx";
import SearchGreeting from "./SearchGreeting.jsx";

const FILTERS = [
  { id: "combined", label: "Combined", icon: Search },
  { id: "video", label: "Videos", icon: Video },
  { id: "book", label: "Books", icon: BookOpen },
];

function filterResults(results, filter) {
  if (filter === "combined") {
    return results;
  }
  return results.filter((result) => result.type === filter);
}

function useSpeechSearch(onTranscript) {
  const [listening, setListening] = useState(false);

  const start = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognition.onresult = (event) => {
      const text = event.results?.[0]?.[0]?.transcript || "";
      if (text.trim()) {
        onTranscript(text.trim());
      }
    };
    recognition.start();
  };

  return { listening, start };
}

export default function SearchPage({ sessions, onSearch, onFilterChange }) {
  const [inputValue, setInputValue] = useState("");
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const { listening, start } = useSpeechSearch((text) => {
    setInputValue(text);
    onSearch(text);
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [sessions]);

  const hasSessions = sessions.length > 0;
  const latestLoading = sessions.some((session) => session.loading);

  const handleSubmit = (event) => {
    event.preventDefault();
    const query = inputValue.trim();
    if (!query) {
      inputRef.current?.focus();
      return;
    }
    setInputValue("");
    onSearch(query);
  };

  const searchForm = (
    <form className={`searchComposer ${hasSessions ? "floating" : "inline"}`} onSubmit={handleSubmit}>
      <button
        type="button"
        className={`composerIcon ${listening ? "recording" : ""}`}
        onClick={start}
        aria-label="Voice search"
        title="Voice search"
      >
        <Mic size={20} />
      </button>
      <input
        ref={inputRef}
        value={inputValue}
        onChange={(event) => setInputValue(event.target.value)}
        placeholder="Ask about discipline, training, recovery, fat loss..."
      />
      <button className="submitButton" type="submit" aria-label="Search">
        <ArrowUp size={20} />
      </button>
    </form>
  );

  const content = !hasSessions ? (
    <SearchGreeting onSearch={onSearch}>{searchForm}</SearchGreeting>
  ) : (
    sessions.map((session) => {
      const visibleResults = filterResults(session.results || [], session.selectedFilter).slice(0, 5);
      return (
        <section className="searchSession" key={session.id}>
          <div className="userBubble">{session.query}</div>

          {session.loading && (
            <div className="loadingRow">
              <Loader2 className="spin" size={22} />
            </div>
          )}

          {!session.loading && session.error && <div className="errorBox">{session.error}</div>}

          {!session.loading && !session.error && (
            <div className="answerBlock">
              <div className="filterBar" role="tablist" aria-label="Result filter">
                {FILTERS.map(({ id, label, icon: Icon }) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={session.selectedFilter === id}
                    className={session.selectedFilter === id ? "active" : ""}
                    key={id}
                    onClick={() => onFilterChange(session.id, id)}
                  >
                    <Icon size={15} />
                    {label}
                  </button>
                ))}
              </div>

              {visibleResults.length === 0 && <p className="emptyResults">No matching results.</p>}
              <div className="resultsList">
                {visibleResults.map((result) =>
                  result.type === "book" ? (
                    <BookResultCard result={result} key={result.id} />
                  ) : (
                    <ResultCard result={result} key={result.id} />
                  ),
                )}
              </div>
              <RelatedQuestions questions={session.related_queries || []} onSelect={onSearch} />
            </div>
          )}
        </section>
      );
    })
  );

  return (
    <div className="searchPage">
      <main className="threadPanel">
        <header className="topBar">
          <div>
            <span className="eyebrow">codex_project</span>
            <h1>Motivation Search</h1>
          </div>
          {latestLoading && <Loader2 className="spin" size={20} />}
        </header>

        <div className="threadStream">
          {content}
          <div ref={bottomRef} />
        </div>

        {hasSessions && searchForm}
      </main>

      <MotivationRail onSearch={onSearch} />
    </div>
  );
}
