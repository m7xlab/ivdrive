import type { MetadataRoute } from "next";

export const dynamic = "force-static";

const base = "https://ivdrive.eu";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${base}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/features/`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/open-source/`, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/community/`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${base}/roadmap/`, changeFrequency: "weekly", priority: 0.7 },
    { url: `${base}/sponsors/`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${base}/about/`, changeFrequency: "monthly", priority: 0.5 },
  ];
}
