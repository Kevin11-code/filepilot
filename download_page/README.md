# FilePilot Download Page

A modern, responsive download page for FilePilot - Secure SFTP Client.

## Features

- 🎨 Modern, responsive design
- 🚀 Optimized for Vercel deployment
- 📱 Mobile-friendly interface
- ⚡ Fast loading with optimized assets
- 🔒 Security-focused messaging
- 📥 Easy download experience

## Deployment to Vercel

### Option 1: Vercel CLI

1. Install Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy from this directory:
   ```bash
   cd download_page
   vercel
   ```

### Option 2: GitHub Integration

1. Push this folder to a GitHub repository
2. Connect your GitHub account to Vercel
3. Import the project in Vercel dashboard
4. Deploy automatically

### Option 3: Drag & Drop

1. Zip the contents of this folder
2. Go to [vercel.com](https://vercel.com)
3. Drag and drop the zip file

## File Structure

```
download_page/
├── index.html          # Main HTML file
├── styles.css          # Stylesheet
├── script.js           # JavaScript functionality
├── package.json        # Project configuration
├── vercel.json         # Vercel deployment config
├── assets/
│   └── filePilotIcon.png  # Logo file
├── downloads/          # Directory for binary files
│   ├── FilePilot-Setup.exe  # Windows installer (add your file here)
│   └── filepilot-linux     # Linux binary (add your file here)
└── README.md           # This file
```

## Adding Download Files

Before deployment, add your actual binary files to the `downloads/` directory:

1. **Windows**: Place your `.exe` installer as `downloads/FilePilot-Setup.exe`
2. **Linux**: Place your Linux binary as `downloads/filepilot-linux`

## Customization

### Update Links
- Replace GitHub links in the navigation and footer
- Update contact email in the footer
- Modify download file names if different

### Styling
- Colors can be customized in `styles.css`
- Update the CSS custom properties at the top of the file
- Modify breakpoints for responsive design

### Content
- Update version numbers and system requirements
- Modify feature descriptions
- Update installation instructions

## Performance Optimizations

- Images are optimized and cached
- CSS and JS are minified for production
- Proper caching headers are set via `vercel.json`
- Fonts are loaded efficiently from Google Fonts

## Analytics (Optional)

To add analytics tracking, uncomment and configure the analytics code in `script.js`:

```javascript
// Example for Google Analytics
gtag('event', 'download', {
    'platform': platform,
    'version': '1.0.0'
});
```

## Support

For issues with the download page, please check:
1. File paths are correct
2. Binary files are uploaded to `downloads/` directory
3. Vercel deployment completed successfully

## License

This download page is part of the FilePilot project and follows the same license.
