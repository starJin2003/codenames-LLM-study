# Codenames LLM Study

An interactive web-based sandbox for exploring and testing covert channel coordination between LLMs playing Codenames.

## Features
- **Shared Instructions Configuration**: Edit Codenames base rules and custom protocol strategy prompts in real-time.
- **Interactive Board Editor**: Edit the words and roles of the 5x5 board tiles (Red = Target, Gray = Civilian) or reroll randomly.
- **Simulation Runner**: Run the game using Gemini 3.1 Flash-Lite to see how the Codemaster encodes and the Guesser decodes indices.
- **LLM Query Log**: Access a detailed timeline showing raw prompts and response payloads for API calls.

## How to Run

1. Make sure you have Node.js installed.
2. Navigate to the `web/` directory.
3. Configure your Google Gemini API Key in `web/.env.local`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
4. Install dependencies and start the development server:
   ```bash
   npm install
   npm run dev
   ```
5. Open [http://localhost:3000](http://localhost:3000) in your browser.
