import React from 'react';

/**
 * useHoverProps — runtime replacement for the prototype's `style-hover`
 * attribute (which plain React inline styles cannot express, since `&:hover`
 * inside a style object is silently ignored).
 *
 * Usage (hook, for fixed-position elements):
 *   const hov = useHoverProps(buttonStyle, hoverStyle);
 *   <button {...hov}>…</button>
 *
 * Usage (component, safe inside `.map()` / conditionals):
 *   <Hover as="button" base={buttonStyle} hover={hoverStyle} onClick={…}>…</Hover>
 */
export function useHoverProps(base, hover) {
  const [on, setOn] = React.useState(false);
  return {
    style: on && hover ? { ...base, ...hover } : base,
    onMouseEnter: () => setOn(true),
    onMouseLeave: () => setOn(false),
  };
}

/**
 * Hover — declarative wrapper so hover state can be used inside lists,
 * maps and conditional branches without breaking the rules of hooks.
 * Renders `as` (default `button`) with merged base/hover styles.
 */
export function Hover({ as: Tag = 'button', base, hover, children, ...rest }) {
  const p = useHoverProps(base, hover);
  return (
    <Tag {...rest} {...p}>
      {children}
    </Tag>
  );
}

export default useHoverProps;
