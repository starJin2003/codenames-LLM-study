import "./globals.css";

export const metadata = {
  title: "Codenames Covert Channel Sandbox",
  description: "Tinker with prompts and boards to see how LLMs communicate hidden bitmasks in oneshot games.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
