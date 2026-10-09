// SerienStream (serienstream.to) through SerienStreamAPI (https://github.com/IcySnex/SerienStreamAPI), for
// NotFlix's series: the desktop app runs this on the PC and its pages ask it directly.
//
//   GET /health
//   GET /search?q=                                          series matching the text
//   GET /series/{slug}                                      one series: title, text, banner, seasons
//   GET /series/{slug}/seasons/{season}                     the season's episodes (0: the movies)
//   GET /series/{slug}/seasons/{season}/episodes/{episode}  the episode's streams (season 0: movie)
//
// {slug} is the series' name in the site's addresses (serienstream.to/serie/<slug>). A series, season or
// episode that doesn't exist answers 404. Settings: SERIES_HOST (default https://serienstream.to/), --urls.

using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using SerienStreamAPI.Client;
using SerienStreamAPI.Exceptions;

var builder = WebApplication.CreateSlimBuilder(args);
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter());
});
builder.Logging.SetMinimumLevel(LogLevel.Warning);

var host = Environment.GetEnvironmentVariable("SERIES_HOST") is { Length: > 0 } configured
    ? configured
    : "https://serienstream.to/";
if (!host.EndsWith('/')) host += "/";
var client = new SerienStreamClient(host, "serie");
var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = true }) { BaseAddress = new Uri(host), Timeout = TimeSpan.FromSeconds(20) };
http.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64) NotFlix");
var coverCache = new Dictionary<string, Dictionary<string, string>>();
var downloader = new DownloadClient("ffmpeg", false, null);
var app = builder.Build();

app.MapGet("/resolve", async (string url, string hoster, CancellationToken ct) =>
    await Answer(async () =>
    {
        var direct = hoster switch
        {
            "VOE" => await downloader.GetVoeStreamUrlAsync(url, ct),
            "Streamtape" => await downloader.GetStreamtapeStreamUrlAsync(url, ct),
            "Doodstream" => await downloader.GetDoodstreamStreamUrlAsync(url, ct),
            "Vidoza" => await downloader.GetVidozaStreamUrlAsync(url, ct),
            _ => throw new NotSupportedException($"{hoster} can't be resolved"),
        };
        return Results.Ok(new { url = direct });
    }));

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet("/search", async (string q, CancellationToken ct) =>
    await Answer(async () => Results.Ok(await Search(q.Trim(), ct))));

app.MapGet("/series/{slug}", async (string slug, CancellationToken ct) =>
    await Answer(async () =>
    {
        var series = await client.GetSeriesAsync(slug, ct);
        return Results.Ok(new
        {
            slug,
            title = series.Title,
            description = series.Description,
            banner = Absolute(series.BannerUrl),
            cover = (await Covers(series.Title, ct)).GetValueOrDefault(slug),
            yearStart = series.YearStart,
            yearEnd = series.YearEnd,
            genres = series.Genres,
            seasons = series.SeasonsCount,
            hasMovies = series.HasMovies,
        });
    }));

app.MapGet("/series/{slug}/seasons/{season:int}", async (string slug, int season, CancellationToken ct) =>
    await Answer(async () =>
    {
        var episodes = season == 0
            ? await client.GetMoviesAsync(slug, ct)
            : await client.GetEpisodesAsync(slug, season, ct);
        return Results.Ok(episodes.Select(e => new
        {
            number = e.Number,
            title = e.Title,
            originalTitle = e.OriginalTitle,
            hosters = e.Hosters.Select(h => h.ToString()),
            languages = e.Languages.Select(l => new { audio = l.Audio.ToString(), subtitle = l.Subtitle?.ToString() }),
        }));
    }));

app.MapGet("/series/{slug}/seasons/{season:int}/episodes/{episode:int}",
    async (string slug, int season, int episode, CancellationToken ct) =>
        await Answer(async () =>
        {
            var details = season == 0
                ? await client.GetMovieVideoInfoAsync(slug, episode, ct)
                : await client.GetEpisodeVideoInfoAsync(slug, episode, season, ct);
            return Results.Ok(new
            {
                number = details.Number,
                season = details.Season,
                title = details.Title,
                originalTitle = details.OriginalTitle,
                description = details.Description,
                streams = details.Streams.Select(s => new
                {
                    url = Absolute(s.VideoUrl),
                    hoster = s.Hoster.ToString(),
                    audio = s.Language.Audio.ToString(),
                    subtitle = s.Language.Subtitle?.ToString(),
                }),
            });
        }));

app.Run();

string? Absolute(string? url)
{
    if (string.IsNullOrWhiteSpace(url)) return null;
    return Uri.TryCreate(new Uri(host), url, out var uri) ? uri.ToString() : url;
}

// The site's own search (the library only fetches a series whose name it already knows): a
// list of series. When it can't be used, the text itself is tried as a series name.
async Task<List<Hit>> Search(string query, CancellationToken ct)
{
    var found = new List<Hit>();
    if (query.Length == 0) return found;
    var seen = new HashSet<string>();
    try
    {
        using var response = await http.GetAsync($"api/search/suggest?term={Uri.EscapeDataString(query)}", ct);
        response.EnsureSuccessStatusCode();
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));
        if (json.RootElement.TryGetProperty("shows", out var shows) && shows.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in shows.EnumerateArray())
            {
                var url = item.TryGetProperty("url", out var u) ? u.GetString() ?? "" : "";
                var match = Regex.Match(url, @"^/serie/(?:stream/)?([^/?#]+)/?$");
                if (!match.Success || !seen.Add(match.Groups[1].Value)) continue;
                found.Add(new Hit(match.Groups[1].Value, Text(item, "name"), "", null));
            }
        }
    }
    catch (Exception e) when (e is HttpRequestException or JsonException or TaskCanceledException && !ct.IsCancellationRequested)
    {
        // Falls through to the exact name below.
    }
    if (found.Count == 0)
    {
        var slug = Regex.Replace(query.ToLowerInvariant(), @"[^a-z0-9]+", "-").Trim('-');
        try
        {
            var series = await client.GetSeriesAsync(slug, ct);
            found.Add(new Hit(slug, series.Title, series.Description, null));
        }
        catch (Exception e) when (e is SeriesNotFoundException or HttpRequestException) { }
    }
    // The covers: the site's own results page shows them (the suggestions don't).
    var covers = await Covers(query, ct);
    var withCovers = found.Select(h => h with { Image = covers.GetValueOrDefault(h.Slug) }).ToList();
    // Hits the results page doesn't show: their own title finds them (a few, at the same time).
    await Parallel.ForEachAsync(
        withCovers.Select((h, i) => (h, i)).Where(x => x.h.Image is null).Take(8).ToList(),
        new ParallelOptions { MaxDegreeOfParallelism = 4, CancellationToken = ct },
        async (x, token) =>
        {
            var own = await Covers(x.h.Title, token);
            if (own.GetValueOrDefault(x.h.Slug) is { } image) withCovers[x.i] = x.h with { Image = image };
        });
    return withCovers;
}

// slug -> cover address, from the site's results page for a text (kept, so a series page and
// the search it came from share one request).
async Task<Dictionary<string, string>> Covers(string term, CancellationToken ct)
{
    var key = term.Trim().ToLowerInvariant();
    lock (coverCache)
    {
        if (coverCache.TryGetValue(key, out var known)) return known;
    }
    var covers = new Dictionary<string, string>();
    try
    {
        var html = await http.GetStringAsync($"suche?term={Uri.EscapeDataString(term)}", ct);
        foreach (Match m in Regex.Matches(html, @"href=""/serie/(?:stream/)?([^""/?#]+)""\s+class=""d-block show-cover""[\s\S]{0,4000}?<img\s+(?:data-)?src=""(/media/images/[^""]+)"""))
        {
            if (Absolute(m.Groups[2].Value) is { } cover) covers.TryAdd(m.Groups[1].Value, cover);
        }
    }
    catch (Exception e) when (e is HttpRequestException or TaskCanceledException && !ct.IsCancellationRequested)
    {
        return covers; // no covers this time, and not remembered
    }
    lock (coverCache)
    {
        if (coverCache.Count > 200) coverCache.Clear();
        coverCache[key] = covers;
    }
    return covers;
}

static string Text(JsonElement item, string name) =>
    item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
        ? Regex.Replace(value.GetString() ?? "", "<[^>]+>", "").Trim()
        : "";

static async Task<IResult> Answer(Func<Task<IResult>> work)
{
    try
    {
        return await work();
    }
    catch (Exception e) when (e is SeriesNotFoundException or SeasonNotFoundException
        or EpisodeNotFoundException or MovieNotFoundException)
    {
        return Results.NotFound(new { detail = e.Message });
    }
    catch (HttpRequestException e) when (e.StatusCode == System.Net.HttpStatusCode.NotFound)
    {
        return Results.NotFound(new { detail = e.Message });
    }
    catch (Exception e)
    {
        return Results.Problem(e.Message, statusCode: 502);
    }
}

record Hit(string Slug, string Title, string Description, string? Image);
