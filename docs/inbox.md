# Inbox Worker

The inbox worker automates publishing videos by watching a folder or reading from a Google Sheet. It processes videos that are submitted via either method and publishes them using your configured settings.

## Profiles

The tool supports multiple profiles, allowing different configurations for different channels or use cases. For example, the `config.cvscc.yaml` file provides a configuration for the Chippewa Valley Sports Car Club. Each profile can have its own `paths.credentials_dir` and other settings.

## Folder Source

When using the folder source, videos are published from a local folder:

1. Place your video files (`.mp4`, `.mov`, `.m4v`) in a folder
2. Optionally, include a sidecar YAML file with the same stem (e.g., `video.mp4` with `video.yaml`)
3. The inbox worker will automatically process videos

### Marker Files

The inbox worker uses marker files to track state:

- `.processing`: Created when an item is being processed (prevents concurrent processing)
- `.published.json`: Created when an item is successfully published
- `.failed.txt`: Created when an item fails to publish

### Folder Layout

The folder layout when using `--source folder`:

```
videos/
├── run.mp4
├── run.yaml     # Optional sidecar with overrides
├── race.mov
├── race.yaml    # Optional sidecar with overrides
├── .processing  # Marker file when processing
├── .published.json  # Marker file when published
└── .failed.txt  # Marker file when failed
```

If a video file is missing when a `.processing` marker is found, the item is considered "stuck" and will be reported as a warning.

## Google Sheet Source

When using the sheet source, videos come from a Google Sheet:

1. Create a Google Sheet with the required columns (see below)
2. Configure `inbox.sheet_id` and `inbox.sheet_name` in your config
3. Run the inbox worker with `--source sheet`

### Sheet Columns

The inbox worker reads from the following columns:

- `file`: Google Drive file ID or URL (required) 
- `title`: Override for the video title (optional)
- `submitter`: Name of the submitter (optional)
- `publish`: Set to `true` to queue the video for publishing (required)
- `status`: Automatically managed by the inbox worker (do not edit)
- `links`: Automatically populated with published links (do not edit)
- `error`: Automatically populated with error messages (do not edit)
- `config`: YAML snippet for per-video overrides (optional)
- Any column name that matches a per-video config key (see below)

### Reserved Columns

The following column names are reserved and cannot be used for per-video overrides:

- `file`
- `title` 
- `submitter`
- `publish`
- `status`
- `links`
- `error`

### Per-Video Configuration

You can override any per-video setting in a Google Sheet by adding a column with the setting name. For example:

- `teaser.start_seconds` - Override the teaser start time in seconds
- `teaser.overlay.text` - Override the overlay text
- `tags` - Override the video tags
- `youtube.category_id` - Override the YouTube category ID

### Column Naming

Column headers are case-insensitive and can be in any order. The header names match the YAML configuration keys exactly, using dot notation for nested settings.

### Example Sheet Row

| file | title | submitter | publish | teaser.start_seconds | teaser.overlay.text | config |
|------|-------|-----------|---------|----------------------|---------------------|--------|
| 1a2b3c4d5e6f7g8h9i0j | SCCA Run 3 | Isaac | true | 5.0 | Full run on YouTube | {social: {platforms: [tiktok]}} |

In this example:
- The video file is specified by its Drive ID
- The title is overridden to "SCCA Run 3"
- The submitter is "Isaac"
- The publish checkbox is true (it will be published)
- The teaser starts at 5 seconds into the video
- The overlay text is customized
- The config cell contains YAML to override the social platforms to only TikTok

### Configuration Example

```yaml
inbox:
  folder: "videos"
  poll_seconds: 60
  notify_webhook: ""
  sheet_id: "1a2b3c4d5e6f7g8h9i0j"
  sheet_name: "Sheet1"
```

## Running the Worker

To run the inbox worker:

```bash
python inbox.py --config config.yaml --source folder --once
```

Or continuously:

```bash
python inbox.py --config config.yaml --source folder
```

To use the Google Sheet source:

```bash
python inbox.py --config config.yaml --source sheet --once
```

## Discord Notice

When using the inbox worker, you can configure a webhook URL in the inbox configuration to receive notifications about published videos.

For example, to get notified on Discord:

```yaml
inbox:
  folder: "videos"
  poll_seconds: 60
  notify_webhook: "https://discord.com/api/webhooks/..."
```

## Testing the Setup

To test your configuration without actually publishing:

```bash
python inbox.py --config config.yaml --source folder --dry-run
```

This will validate the configuration and show what would be published without actually uploading anything.