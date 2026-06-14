import { Clock3, Dumbbell, Library, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { getExperiences, getVideos } from "../utils/api.js";

function formatTime(seconds) {
  if (seconds === null || seconds === undefined) {
    return "";
  }
  const value = Math.max(0, Math.floor(Number(seconds || 0)));
  const minutes = Math.floor(value / 60);
  const secs = value % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export default function MotivationRail({ onSearch }) {
  const [experiences, setExperiences] = useState([]);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([getExperiences(), getVideos()])
      .then(([experienceResult, videoResult]) => {
        if (cancelled) {
          return;
        }
        if (experienceResult.status === "fulfilled") {
          setExperiences(experienceResult.value.slice(0, 4));
        }
        if (videoResult.status === "fulfilled") {
          setVideos(videoResult.value.slice(0, 3));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasExperiences = experiences.length > 0;
  const hasVideos = videos.length > 0;
  const totalItems = experiences.length + videos.length;
  const contentId = "motivation-rail-content";

  if (loading || (!hasExperiences && !hasVideos)) {
    return null;
  }

  return (
    <aside className={`motivationRail ${isCollapsed ? "railCollapsed" : ""}`} aria-label="Motivation feed">
      <div className="railTop">
        <div className="railTitleBlock">
          <span className="railKicker">{isCollapsed ? "Show library" : "Sources"}</span>
          <strong>{isCollapsed ? `${totalItems} available` : `${totalItems} items`}</strong>
        </div>
        <button
          className="railToggle"
          type="button"
          aria-controls={contentId}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? "Expand motivation sidebar" : "Collapse motivation sidebar"}
          title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setIsCollapsed((value) => !value)}
        >
          {isCollapsed ? <PanelRightOpen size={18} /> : <PanelRightClose size={18} />}
        </button>
      </div>

      {isCollapsed ? (
        <div className="railCollapsedBody" id={contentId}>
          {hasExperiences && (
            <button
              className="railMiniStat"
              type="button"
              title={`${experiences.length} experiences`}
              onClick={() => setIsCollapsed(false)}
            >
              <Dumbbell size={17} />
              <span>{experiences.length}</span>
            </button>
          )}
          {hasVideos && (
            <button
              className="railMiniStat"
              type="button"
              title={`${videos.length} library items`}
              onClick={() => setIsCollapsed(false)}
            >
              <Library size={17} />
              <span>{videos.length}</span>
            </button>
          )}
        </div>
      ) : (
        <div className="railContent" id={contentId}>
          {hasExperiences && (
            <section className="railSection">
              <div className="railHeading">
                <span>
                  <Dumbbell size={18} />
                  <h2>Experiences</h2>
                </span>
                <strong>{experiences.length}</strong>
              </div>
              {experiences.map((item) => (
                <button
                  className="experienceItem"
                  type="button"
                  key={item.experience_id || `${item.video_id}-${item.title}`}
                  onClick={() => onSearch(item.lesson || item.title || item.summary)}
                >
                  <span className="railItemTitle">{item.title || "Training experience"}</span>
                  <small>
                    <Clock3 size={13} />
                    {formatTime(item.start_time_seconds)}
                  </small>
                </button>
              ))}
            </section>
          )}

          {hasVideos && (
            <section className="railSection">
              <div className="railHeading">
                <span>
                  <Library size={18} />
                  <h2>Library</h2>
                </span>
                <strong>{videos.length}</strong>
              </div>
              {videos.map((video) => (
                <button
                  className="libraryItem"
                  type="button"
                  key={video.video_id}
                  onClick={() => onSearch((video.queries && video.queries[0]) || video.title)}
                >
                  <span className="railItemTitle">{video.title || video.video_id}</span>
                  <small>{(video.topics || []).slice(0, 2).join(" / ") || video.difficulty_level}</small>
                </button>
              ))}
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
