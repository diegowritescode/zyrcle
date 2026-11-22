/** The hackathon's Unsplash photos, resized by Unsplash's CDN instead of served at full size. */
export const unsplash = (id: string, width = 1200) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=75`;
