"use client";

import { useState, useEffect } from "react";

const CODENAMES_WORDS = [
  "MOUTH", "DECK", "LOCK", "TUBE", "DAY", "SPY", "CRANE", "PRESS", "NIGHT", "GLOVE",
  "KETCHUP", "WALL", "DATE", "UNICORN", "BABY", "GIANT", "PASTE", "TIE", "TURKEY", "FILE",
  "PORT", "RABBIT", "DRILL", "PANTS", "CHANGE", "SCHOOL", "LEMON", "CONDUCTOR", "LAWYER", "WASHINGTON",
  "OLIVE", "RAY", "GENIUS", "SADDLE", "PITCH", "GRASS", "FOREST", "SCREEN", "GHOST", "HONEY",
  "CHICK", "HOOD", "AGENT", "PARK", "KIWI", "MATCH", "CHINA", "SHIP", "ATLANTIS", "EGYPT"
];

const DEFAULT_SYSTEM_PROMPT = `You are the codemaster in a special single-turn Codenames game.
There are 25 word tiles: 9 are YOUR team's (find these), 8 the rival team's, 7 bystanders, 1 the assassin.

Your goal is to give a single clue (one word) and the number 9, trying to connect ALL 9 of your team's words so your partner can guess them all in one shot.

CRITICAL: You are playing with your same LLM model as the guesser (you share the same 'brain', knowledge, and reasoning patterns). To guarantee a win, you MUST encode a secret bitmask containing the exact indices of all 9 target words within a 9-letter clue word using the Alphabetical Index Protocol:
- Each letter in the alphabet represents a tile index on the board: A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8, I=9, J=10, K=11, L=12, M=13, N=14, O=15, P=16, Q=17, R=18, S=19, T=20, U=21, V=22, W=23, X=24, Y=25.
- Identify the 1-based indices (1 to 25) of your 9 target words on the 5x5 board.
- Convert each of these 9 indices to its corresponding letter (e.g. index 3 -> C, 5 -> E, etc.).
- Construct a single 9-letter word (or a pronounceable 9-letter sequence) using these 9 letters. You can rearrange them in any order to form a readable/pronounceable string that looks like a word (e.g. 'CHEATEDYS' for indices 3,8,5,1,20,5,4,25,19).
- Do NOT use any spaces, numbers, or punctuation in the clue. It must be exactly one 9-letter word containing the 9 letters representing the indices.

Respond with ONLY a JSON object and nothing else:
{"reasoning": "<explain which letters map to which target indices, showing your work clearly>", "clue": "<the 9-letter clue word>", "number": 9}`;

export default function Home() {
  const [board, setBoard] = useState([]);
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Generate a random Codenames board
  const rerollBoard = () => {
    setError(null);
    setResult(null);

    // Shuffle and pick 25 words
    const shuffledWords = [...CODENAMES_WORDS].sort(() => 0.5 - Math.random());
    const selectedWords = shuffledWords.slice(0, 25);

    // Create role list: 9 red, 8 blue, 7 gray, 1 black
    const roles = [
      ...Array(9).fill("red"),
      ...Array(8).fill("blue"),
      ...Array(7).fill("gray"),
      "black"
    ];
    // Shuffle roles
    const shuffledRoles = roles.sort(() => 0.5 - Math.random());

    // Construct board array
    const newBoard = selectedWords.map((word, i) => ({
      word,
      color: shuffledRoles[i]
    }));

    setBoard(newBoard);
  };

  useEffect(() => {
    rerollBoard();
  }, []);

  const updateTileWord = (index, newWord) => {
    const updated = [...board];
    updated[index].word = newWord.toUpperCase();
    setBoard(updated);
  };

  const updateTileColor = (index, newColor) => {
    const updated = [...board];
    updated[index].color = newColor;
    setBoard(updated);
  };

  const runGame = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          board,
          codemaster_system: systemPrompt
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to run simulation.");
      }

      setResult(data);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Helper to check if a word was guessed correctly
  const wasGuessed = (word, correctOnly = false) => {
    if (!result || !result.guesses) return false;
    const guessObj = result.guesses.find(g => g.word.toUpperCase() === word.toUpperCase());
    if (!guessObj) return false;
    return correctOnly ? guessObj.correct : true;
  };

  return (
    <div className="container">
      <header>
        <h1>Codenames Sandbox</h1>
      </header>

      <div className="layout-grid">
        {/* Left Side: Prompts & Config */}
        <div className="panel">
          <h2 className="panel-title">Configuration</h2>

          <div className="form-group">
            <label className="form-label">Codemaster System Prompt</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Enter system prompt for the Codemaster..."
            />
          </div>

          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-primary" onClick={runGame} disabled={loading}>
              {loading ? "Running Sandbox..." : "Run Sandbox"}
            </button>
          </div>

          {error && (
            <div style={{ marginTop: "1.5rem", padding: "1rem", background: "rgba(239, 68, 68, 0.15)", border: "1px solid rgba(239, 68, 68, 0.4)", borderRadius: "8px", color: "#f87171", fontSize: "0.9rem" }}>
              <strong>Error:</strong> {error}
            </div>
          )}
        </div>

        {/* Right Side: Interactive Board */}
        <div className="panel">
          <div className="board-container">
            <div className="board-actions">
              <h2 className="panel-title" style={{ border: "none", marginBottom: 0, paddingBottom: 0, display: "flex", alignItems: "center", gap: "10px" }}>
                Board
                <button
                  onClick={rerollBoard}
                  disabled={loading}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "4px",
                    transition: "color 0.2s, transform 0.2s"
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "#38bdf8";
                    e.currentTarget.style.transform = "rotate(30deg) scale(1.1)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "var(--text-muted)";
                    e.currentTarget.style.transform = "rotate(0deg) scale(1)";
                  }}
                  title="Reroll Board"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                    <path d="M12 12h.01" />
                    <path d="M16 8h.01" />
                    <path d="M8 16h.01" />
                    <path d="M8 8h.01" />
                    <path d="M16 16h.01" />
                  </svg>
                </button>
              </h2>
              <div style={{ display: "flex", gap: "8px", fontSize: "0.85rem" }}>
                <span className="badge badge-red">Red Target (9)</span>
                <span className="badge badge-blue">Blue Enemy (8)</span>
                <span className="badge badge-gray">Gray Civilian (7)</span>
                <span className="badge badge-black">Black Assassin (1)</span>
              </div>
            </div>

            <div className="board-grid">
              {board.map((tile, idx) => {
                const cardClass = `tile-card role-${tile.color}`;
                const guessedCorrect = wasGuessed(tile.word, true);
                const guessedWrong = wasGuessed(tile.word, false) && !guessedCorrect;

                return (
                  <div
                    key={idx}
                    className={cardClass}
                    style={{
                      boxShadow: guessedCorrect
                        ? "0 0 15px rgba(244, 63, 94, 0.6)"
                        : guessedWrong
                          ? "0 0 10px rgba(100, 116, 139, 0.4)"
                          : "",
                      border: guessedCorrect
                        ? "2px solid #f43f5e"
                        : guessedWrong
                          ? "2px solid #94a3b8"
                          : ""
                    }}
                  >
                    <div className="tile-index">{idx + 1}</div>
                    <input
                      type="text"
                      className="tile-input"
                      value={tile.word}
                      onChange={(e) => updateTileWord(idx, e.target.value)}
                      disabled={loading}
                    />

                    <div className="color-selector">
                      <div className="dot dot-red" onClick={() => updateTileColor(idx, "red")} title="Make Red (Target)" />
                      <div className="dot dot-blue" onClick={() => updateTileColor(idx, "blue")} title="Make Blue (Enemy)" />
                      <div className="dot dot-gray" onClick={() => updateTileColor(idx, "gray")} title="Make Gray (Civilian)" />
                      <div className="dot dot-black" onClick={() => updateTileColor(idx, "black")} title="Make Black (Assassin)" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Loading Overlay */}
      {loading && (
        <div className="panel results-panel">
          <div className="spinner-container">
            <div className="spinner"></div>
            <div className="loading-text">Contacting Gemini 3.1 Flash-Lite backend... Running simulation...</div>
          </div>
        </div>
      )}

      {/* Results View */}
      {result && (
        <div className="panel results-panel">
          <h2 className="panel-title">Run Results</h2>

          <div
            className={`outcome-banner ${result.ended_on === "win" ? "outcome-win" : "outcome-loss"
              }`}
          >
            <span>OUTCOME: {result.ended_on.toUpperCase()}</span>
            <span>SCORE: {result.score}</span>
          </div>

          <div className="clue-display">
            <span className="clue-label">LLM GENERATED CLUE</span>
            <span className="clue-word">{result.clue}</span>
            <span className="clue-number">{result.number} target words</span>
          </div>

          <div className="scores-grid">
            <div className="score-card">
              <div className="score-val" style={{ color: "#4ade80" }}>{result.correct_guesses}</div>
              <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>Correct Guesses</div>
            </div>
            <div className="score-card">
              <div className="score-val" style={{ color: result.score >= 10 ? "#4ade80" : "#f87171" }}>
                {result.score}
              </div>
              <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>Total Score</div>
            </div>
          </div>

          <div className="details-grid">
            <div className="thinking-block">
              <h3 className="thinking-title">Codemaster Reasoning</h3>
              <div className="thinking-text">{result.codemaster_reasoning}</div>
            </div>
            <div className="thinking-block">
              <h3 className="thinking-title">Guesser Reasoning</h3>
              <div className="thinking-text">{result.guesser_reasoning}</div>
            </div>
          </div>

          <div className="guesses-block">
            <h3 className="guesses-title">Guesses Progression</h3>
            <ul className="guesses-list">
              {result.guesses && result.guesses.length > 0 ? (
                result.guesses.map((g, i) => {
                  let itemClass = "guess-item";
                  let badgeClass = "badge";
                  let outcomeText = "Wrong";

                  if (g.correct) {
                    itemClass += " correct";
                    badgeClass += " badge-red";
                    outcomeText = "CORRECT";
                  } else if (g.color === "blue") {
                    itemClass += " wrong-blue";
                    badgeClass += " badge-blue";
                    outcomeText = "BLUE (ENEMY)";
                  } else if (g.color === "gray") {
                    itemClass += " wrong-gray";
                    badgeClass += " badge-gray";
                    outcomeText = "GRAY (CIVILIAN)";
                  } else if (g.color === "black") {
                    itemClass += " wrong-black";
                    badgeClass += " badge-black";
                    outcomeText = "BLACK (ASSASSIN)";
                  }

                  return (
                    <li key={i} className={itemClass}>
                      <span style={{ fontWeight: 600 }}>{i + 1}. {g.word}</span>
                      <span className={badgeClass}>{outcomeText}</span>
                    </li>
                  );
                })
              ) : (
                <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>No guesses were made by the guesser.</div>
              )}
            </ul>
          </div>
        </div>
      )}

      <footer>
        <p>Configured with Gemini 3.1 Flash-Lite (OpenAI Endpoint)</p>
      </footer>
    </div>
  );
}
