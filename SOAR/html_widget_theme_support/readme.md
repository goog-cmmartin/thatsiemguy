# Google SecOps SOAR HTML Widget Theme Support with Tailwind CSS

This repository provides an example HTML file (`tailwind_css_example.html`) that demonstrates how to create a Google SecOps SOAR HTML widget with support for light and dark themes using Tailwind CSS.

## How it Works

The example uses a combination of Tailwind CSS, CSS variables, and a small amount of JavaScript to achieve theme switching.

1.  **Tailwind CSS:** The UI components are styled using Tailwind CSS utility classes.
2.  **CSS Variables:** The colors used in the Tailwind CSS configuration are defined as CSS variables (e.g., `var(--widget-bg-color)`).
3.  **JavaScript:**
    *   A script listens for a `message` event from the SOAR platform, which contains the background color of the theme.
    *   Based on the background color, the script determines if the theme is light or dark.
    *   The appropriate color palette (CSS variables) is then applied to the `body` of the document.

## How to Use

1.  **Include Tailwind CSS:** The example includes Tailwind CSS via a CDN.
2.  **Configure Tailwind CSS:** The `tailwind.config` script is configured to use CSS variables for colors.
3.  **Define Color Palettes:** The `themes` object in the JavaScript code defines the color palettes for the light and dark themes.
4.  **Add Your Content:** The body of the HTML contains a sample widget structure. You can replace this with your own content.

## Theme Simulation

The example includes a "Theme Simulator" that allows you to test the theme switching functionality without having to deploy the widget in a SOAR instance. Clicking the "Simulate Light Mode" and "Simulate Dark Mode" buttons will simulate the `message` event from the SOAR platform and switch the theme accordingly. You can remove the "DEMONSTRATION CONTROLS" section when you are ready to deploy your widget.