import RelatedQuestions from "./RelatedQuestions.jsx";

const SUGGESTIONS = [
  "How do I stay consistent with workouts?",
  "How can I build mental toughness?",
  "What helps beginners lose fat safely?",
  "How do I stop quitting when training gets hard?",
  "How should I recover after a bad week?",
];

export default function SearchGreeting({ children, onSearch }) {
  return (
    <section className="greeting" aria-label="Search start">
      <div className="greetingCopy">
        <span className="sectionLabel">Ask with intent</span>
        <h2>Find the exact training moment that answers the question.</h2>
        <p>Discipline, training, recovery, fat loss, and the hard weeks in between.</p>
      </div>
      {children}
      <div className="suggestionBlock">
        <span className="sectionLabel">Common questions</span>
        <RelatedQuestions questions={SUGGESTIONS} onSelect={onSearch} />
      </div>
    </section>
  );
}
