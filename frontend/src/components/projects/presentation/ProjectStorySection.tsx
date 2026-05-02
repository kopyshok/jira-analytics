import React from 'react';

export const ProjectStorySection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="story-section" style={{ padding: '32px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <h2 style={{ fontSize: 28, fontWeight: 600, color: '#fff', marginBottom: 16 }}>{title}</h2>
    {children}
  </section>
);
