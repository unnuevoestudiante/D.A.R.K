using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using DarkSetup.Downloads;
using DarkSetup.Manifest;
using DarkSetup;

namespace DarkInstaller;

internal sealed class InstallerForm : Form
{
    private static readonly string TermsVersion = ReadTermsVersion();
    private static readonly byte[] TermsBytes = ReadEmbeddedTermsBytes();
    private static readonly string Terms = new UTF8Encoding(false, true).GetString(TermsBytes).TrimStart('\uFEFF');
    private static readonly string TermsSha256 = Convert.ToHexString(SHA256.HashData(TermsBytes)).ToLowerInvariant();
    private readonly Letrero manifestState = new();
    private readonly ListView artifacts = new();
    private readonly TextBox installPath = new();
    private readonly Casilla acceptTerms = new();
    private readonly Tecla installButton = new();
    private readonly Tecla cancelButton = new();
    private readonly BarraHaz progress = new();
    private readonly Letrero status = new();
    private readonly Letrero total = new();
    private readonly Letrero selectedDescription = new();
    private readonly Tecla selectedSource = new();
    private readonly Tecla selectedLicense = new();
    private readonly Tecla thirdPartyNoticesButton = new();
    private readonly Migas migas = new();
    private readonly Letrero puntoEstado = new();
    private readonly ZonaLista zonaLista = new();
    private readonly RichTextBox terms = new();
    private readonly ScrollLateral scrollLista = new();
    private readonly ScrollLateral scrollTerms = new();
    private readonly Panel listaVacia = new PanelBase();
    private readonly ToolTip detailsTip = new();
    private readonly RetryableCancellation cancellation = new();
    private IReadOnlySet<string> allowedSourceHosts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> selectedArtifactIds = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> reviewedLicenseArtifactIds = new(StringComparer.OrdinalIgnoreCase);
    private VerifiedManifest? manifest;
    private bool working;
    private bool setupIsRunning;

    public InstallerForm(string? initialInstallPath = null)
    {
        Text = "D.A.R.K. — Instalador";
        FormBorderStyle = FormBorderStyle.None;
        var area = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1280, 800);
        MinimumSize = new Size(Math.Min(940, area.Width), Math.Min(680, area.Height));
        Size = new Size(Math.Min(1180, area.Width - 40), Math.Min(860, area.Height - 40));
        // Un margen propio deja una franja del formulario libre para los agarres de redimensionado.
        Padding = new Padding(ResizeGrip);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Palette.Background;
        ForeColor = Palette.Text;
        Font = Tipos.Cuerpo;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        FormClosing += (_, eventArgs) =>
        {
            if (!working) return;
            eventArgs.Cancel = true;
            if (!setupIsRunning) cancellation.Cancel();
        };
        BuildLayout();
        if (!string.IsNullOrWhiteSpace(initialInstallPath)) installPath.Text = initialInstallPath;
        LoadReleaseManifest();
    }

    private const int ResizeGrip = 6;
    private const int WmNcHitTest = 0x0084;
    private const int WmGetMinMaxInfo = 0x0024;
    private Tecla? maximizeButton;
    private PanelTabla? marco;
    private Control? cabeceraGrande;

    protected override void WndProc(ref Message message)
    {
        if (message.Msg == WmNcHitTest && WindowState == FormWindowState.Normal)
        {
            base.WndProc(ref message);
            if ((int)message.Result == 1) // HTCLIENT: comprobar si el puntero esta en el borde
            {
                var lParam = message.LParam.ToInt64();
                var punto = PointToClient(new Point((short)(lParam & 0xFFFF), (short)((lParam >> 16) & 0xFFFF)));
                var grip = (int)(ResizeGrip * DeviceDpi / 96F) + 2;
                var izquierda = punto.X < grip;
                var derecha = punto.X >= ClientSize.Width - grip;
                var arriba = punto.Y < grip;
                var abajo = punto.Y >= ClientSize.Height - grip;
                var resultado = (izquierda, derecha, arriba, abajo) switch
                {
                    (true, _, true, _) => 13,
                    (_, true, true, _) => 14,
                    (true, _, _, true) => 16,
                    (_, true, _, true) => 17,
                    (true, _, _, _) => 10,
                    (_, true, _, _) => 11,
                    (_, _, true, _) => 12,
                    (_, _, _, true) => 15,
                    _ => 1,
                };
                message.Result = resultado;
            }
            return;
        }
        base.WndProc(ref message);
    }

    private void ToggleMaximize()
    {
        if (WindowState == FormWindowState.Maximized)
        {
            WindowState = FormWindowState.Normal;
        }
        else
        {
            // Sin borde, Windows maximiza sobre toda la pantalla (tapa la barra de tareas):
            // se limita al area de trabajo del monitor donde esta la ventana.
            var pantalla = Screen.FromControl(this);
            var area = pantalla.WorkingArea;
            MaximizedBounds = new Rectangle(area.X - pantalla.Bounds.X, area.Y - pantalla.Bounds.Y, area.Width, area.Height);
            WindowState = FormWindowState.Maximized;
        }
    }

    protected override void OnSizeChanged(EventArgs eventArgs)
    {
        base.OnSizeChanged(eventArgs);
        if (maximizeButton is not null)
            maximizeButton.Text = WindowState == FormWindowState.Maximized ? "\u2750" : "\u25A1";
        Padding = WindowState == FormWindowState.Maximized ? Padding.Empty : new Padding(ResizeGrip);
        // En ventanas bajas el titulo grande le quita espacio a lo importante (lista y condiciones).
        if (marco is not null && cabeceraGrande is not null)
        {
            var compacta = ClientSize.Height < 800;
            cabeceraGrande.Visible = !compacta;
            marco.RowStyles[1].Height = compacta ? 0 : 104;
        }
    }

    protected override void OnPaintBackground(PaintEventArgs eventArgs)
    {
        var bounds = ClientRectangle;
        using var fondo = new SolidBrush(Palette.Background);
        eventArgs.Graphics.FillRectangle(fondo, bounds);
        var suelo = new Rectangle(0, bounds.Height * 55 / 100, bounds.Width, bounds.Height * 45 / 100);
        if (suelo.Height > 0)
        {
            using var gradiente = new LinearGradientBrush(suelo, Color.Transparent, Palette.Suelo, 90F);
            eventArgs.Graphics.FillRectangle(gradiente, suelo);
        }
        using var filete = new Pen(Color.FromArgb(26, Palette.Cyan), 1F);
        eventArgs.Graphics.DrawRectangle(filete, 0, 0, bounds.Width - 1, bounds.Height - 1);
    }

    private void BuildLayout()
    {
        var frame = new PanelTabla
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            ColumnCount = 1,
            RowCount = 4,
        };
        frame.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
        frame.RowStyles.Add(new RowStyle(SizeType.Absolute, 104));
        frame.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        frame.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));
        Controls.Add(frame);

        marco = frame;
        frame.Controls.Add(BuildChrome(), 0, 0);
        cabeceraGrande = BuildHeader();
        frame.Controls.Add(cabeceraGrande, 0, 1);

        var escenario = new PanelBase { Dock = DockStyle.Fill, BackColor = Color.Transparent };
        var marca = new TesseractGlyph { Opacidad = 0.32F, Size = new Size(470, 470) };
        var card = new MarcoPanel { Padding = new Padding(30, 20, 30, 22) };
        card.Controls.Add(BuildCardContent());
        escenario.Controls.Add(card);
        escenario.Controls.Add(marca);
        marca.SendToBack();
        escenario.Resize += (_, _) =>
        {
            var ancho = Math.Min(escenario.ClientSize.Width - 96, Math.Max(1040, escenario.ClientSize.Width * 72 / 100));
            var alto = escenario.ClientSize.Height - 4;
            card.SetBounds((escenario.ClientSize.Width - ancho) / 2, 2, ancho, alto);
            marca.SetBounds((escenario.ClientSize.Width - marca.Width) / 2,
                (escenario.ClientSize.Height - marca.Height) / 2, marca.Width, marca.Height);
        };
        frame.Controls.Add(escenario, 0, 2);

        detailsTip.OwnerDraw = true;
        detailsTip.BackColor = Palette.Panel;
        detailsTip.ForeColor = Palette.TextMuted;
        detailsTip.Draw += (_, eventArgs) =>
        {
            using var fondo = new SolidBrush(Palette.Panel);
            eventArgs.Graphics.FillRectangle(fondo, eventArgs.Bounds);
            using var borde = new Pen(Color.FromArgb(90, Palette.Cyan), 1F);
            eventArgs.Graphics.DrawRectangle(borde, eventArgs.Bounds.Left, eventArgs.Bounds.Top,
                eventArgs.Bounds.Width - 1, eventArgs.Bounds.Height - 1);
            TextRenderer.DrawText(eventArgs.Graphics, eventArgs.ToolTipText, Tipos.Chica,
                Rectangle.Inflate(eventArgs.Bounds, -8, -4), Palette.TextMuted,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix);
        };
    }

    private Control BuildChrome()
    {
        var chrome = new PanelBase { Dock = DockStyle.Fill, BackColor = Color.Transparent };
        chrome.MouseDown += BeginWindowDrag;
        var layout = new PanelTabla
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(16, 0, 10, 0),
            ColumnCount = 4,
            RowCount = 1,
            BackColor = Color.Transparent,
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 30));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 160));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 124));
        var glyph = new TesseractGlyph { Dock = DockStyle.Fill, Margin = new Padding(0, 8, 4, 8) };
        layout.Controls.Add(glyph, 0, 0);
        var titulo = new Letrero
        {
            Text = "D.A.R.K.  //  INSTALADOR",
            Font = Tipos.Chica,
            Tracking = 0.22F,
            ForeColor = Palette.TextDim,
            Dock = DockStyle.Fill,
        };
        titulo.MouseDown += BeginWindowDrag;
        titulo.MouseDoubleClick += (_, _) => ToggleMaximize();
        layout.Controls.Add(titulo, 1, 0);
        var paquete = new Letrero
        {
            Text = "●  PAQUETE LOCAL",
            Font = Tipos.Micro,
            Tracking = 0.18F,
            ForeColor = Palette.Cyan,
            Alineacion = ContentAlignment.MiddleCenter,
            Dock = DockStyle.Fill,
        };
        paquete.MouseDown += BeginWindowDrag;
        layout.Controls.Add(paquete, 2, 0);
        var botones = new PanelFlujo
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            WrapContents = false,
            BackColor = Color.Transparent,
            Margin = Padding.Empty,
            Padding = new Padding(0, 6, 0, 6),
        };
        var close = new Tecla { Text = "×", Estilo = EstiloTecla.Simbolo, Size = new Size(36, 28), Margin = new Padding(2, 0, 0, 0) };
        close.Click += (_, _) => Close();
        maximizeButton = new Tecla { Text = "\u25A1", Estilo = EstiloTecla.Simbolo, Size = new Size(36, 28), Margin = new Padding(2, 0, 0, 0) };
        maximizeButton.Click += (_, _) => ToggleMaximize();
        var minimize = new Tecla { Text = "—", Estilo = EstiloTecla.Simbolo, Size = new Size(36, 28), Margin = new Padding(2, 0, 0, 0) };
        minimize.Click += (_, _) => WindowState = FormWindowState.Minimized;
        botones.Controls.Add(close);
        botones.Controls.Add(maximizeButton);
        botones.Controls.Add(minimize);
        chrome.MouseDoubleClick += (_, _) => ToggleMaximize();
        layout.Controls.Add(botones, 3, 0);
        chrome.Controls.Add(layout);
        return chrome;
    }

    private Control BuildHeader()
    {
        var header = new PanelTabla
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            BackColor = Color.Transparent,
            Padding = new Padding(0, 14, 0, 0),
        };
        header.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        header.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));
        header.Controls.Add(new Letrero
        {
            Text = "D.A.R.K.  //  INSTALACIÓN",
            Font = Tipos.Titulo,
            Tracking = 0.28F,
            ForeColor = Palette.Brand,
            Alineacion = ContentAlignment.MiddleCenter,
            Dock = DockStyle.Fill,
        }, 0, 0);
        var lineaEstado = new PanelTabla
        {
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 1,
            BackColor = Color.Transparent,
        };
        lineaEstado.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        lineaEstado.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        lineaEstado.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        puntoEstado.Text = "●";
        puntoEstado.Font = Tipos.Micro;
        puntoEstado.ForeColor = Palette.Cyan;
        puntoEstado.AutoSize = false;
        puntoEstado.Size = new Size(16, 20);
        puntoEstado.Alineacion = ContentAlignment.MiddleCenter;
        puntoEstado.Margin = new Padding(0, 3, 6, 3);
        var modo = new Letrero
        {
            Text = "SECUENCIA DE INSTALACIÓN",
            Font = Tipos.Micro,
            Tracking = 0.28F,
            ForeColor = Palette.TextMuted,
            AutoSize = false,
            Size = new Size(330, 20),
            Margin = new Padding(0, 3, 0, 3),
        };
        lineaEstado.Controls.Add(puntoEstado, 0, 0);
        lineaEstado.Controls.Add(modo, 1, 0);
        header.Controls.Add(lineaEstado, 0, 1);
        return header;
    }

    private Control BuildCardContent()
    {
        var content = new PanelTabla
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 9,
            BackColor = Palette.Panel,
        };
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));
        content.RowStyles.Add(new RowStyle(SizeType.Percent, 30));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 66));
        content.RowStyles.Add(new RowStyle(SizeType.Percent, 46));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 52));

        var cabecera = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 2, BackColor = Palette.Panel };
        cabecera.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        cabecera.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        cabecera.Controls.Add(new Letrero
        {
            Text = "// COMPONENTES",
            Font = Tipos.Seccion,
            Tracking = 0.2F,
            ForeColor = Palette.Cyan,
            AutoSize = false,
            Size = new Size(200, 28),
            Margin = new Padding(0, 4, 0, 4),
        }, 0, 0);
        migas.Dock = DockStyle.Fill;
        migas.Font = Tipos.Micro;
        migas.Margin = new Padding(0, 4, 0, 4);
        cabecera.Controls.Add(migas, 1, 0);
        content.Controls.Add(cabecera, 0, 0);

        manifestState.Dock = DockStyle.Fill;
        manifestState.Font = Tipos.Chica;
        manifestState.Tracking = 0.04F;
        manifestState.ForeColor = Palette.Amber;
        manifestState.Recortar = true;
        content.Controls.Add(manifestState, 0, 1);

        zonaLista.Dock = DockStyle.Fill;
        zonaLista.Padding = new Padding(16, 14, 8, 14);
        artifacts.Dock = DockStyle.Fill;
        artifacts.View = View.Details;
        artifacts.CheckBoxes = false;
        artifacts.FullRowSelect = true;
        artifacts.HideSelection = false;
        artifacts.GridLines = false;
        artifacts.BackColor = Palette.Panel;
        artifacts.ForeColor = Palette.Text;
        artifacts.BorderStyle = BorderStyle.None;
        artifacts.HeaderStyle = ColumnHeaderStyle.Nonclickable;
        artifacts.Font = Tipos.Cuerpo;
        artifacts.OwnerDraw = true;
        artifacts.SmallImageList = new ImageList { ImageSize = new Size(1, 28) };
        artifacts.DrawColumnHeader += DrawArtifactHeader;
        artifacts.DrawItem += DrawArtifactRow;
        artifacts.DrawSubItem += DrawArtifactSubItem;
        artifacts.MouseClick += ToggleArtifactAtPointer;
        artifacts.MouseDoubleClick += (_, _) => OpenSelectedLicense();
        artifacts.Columns.Add("COMPONENTE", 200);
        artifacts.Columns.Add("VERSIÓN", 90);
        artifacts.Columns.Add("DESCARGA", 95);
        artifacts.Columns.Add("INSTALADO", 110);
        artifacts.Columns.Add("ARQUITECTURA", 115);
        artifacts.Columns.Add("ACCIÓN", 140);
        artifacts.Columns.Add("TIPO", 90);
        artifacts.Columns.Add("PUBLICADOR", 150);
        artifacts.SelectedIndexChanged += (_, _) => UpdateSelectedArtifactDetails();
        artifacts.Resize += (_, _) =>
        {
            var resto = artifacts.ClientSize.Width;
            for (var i = 0; i < artifacts.Columns.Count - 1; i++) resto -= artifacts.Columns[i].Width;
            if (resto > 90) artifacts.Columns[^1].Width = resto;
            RefrescarScrollLista();
        };
        zonaLista.Controls.Add(artifacts);
        scrollLista.Dock = DockStyle.Right;
        zonaLista.Controls.Add(scrollLista);
        listaVacia.BackColor = Palette.Panel;
        listaVacia.Controls.Add(new Letrero
        {
            Text = "sin componentes — manifiesto no verificado",
            Dock = DockStyle.Fill,
            Font = Tipos.Chica,
            Tracking = 0.08F,
            ForeColor = Palette.TextOff,
            Alineacion = ContentAlignment.MiddleCenter,
        });
        zonaLista.Controls.Add(listaVacia);
        listaVacia.BringToFront();
        zonaLista.Resize += (_, _) => listaVacia.Bounds = artifacts.Bounds;
        content.Controls.Add(zonaLista, 0, 2);

        var details = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 3, BackColor = Palette.Panel, Padding = new Padding(16, 6, 16, 0) };
        details.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        details.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 215));
        details.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 175));
        selectedDescription.Dock = DockStyle.Fill;
        selectedDescription.Font = Tipos.Chica;
        selectedDescription.ForeColor = Palette.TextMuted;
        selectedDescription.Recortar = true;
        selectedDescription.Text = "Selecciona un componente para revisar qué instala, su origen y licencia.";
        details.Controls.Add(selectedDescription, 0, 0);
        selectedSource.Text = "Abrir origen";
        selectedSource.Estilo = EstiloTecla.Texto;
        selectedSource.Dock = DockStyle.Fill;
        selectedSource.Enabled = false;
        selectedSource.Click += (_, _) => OpenSelectedSource();
        details.Controls.Add(selectedSource, 1, 0);
        selectedLicense.Text = "Abrir licencia";
        selectedLicense.Estilo = EstiloTecla.Texto;
        selectedLicense.Dock = DockStyle.Fill;
        selectedLicense.Enabled = false;
        selectedLicense.Click += (_, _) => OpenSelectedLicense();
        details.Controls.Add(selectedLicense, 2, 0);
        content.Controls.Add(details, 0, 3);

        var destino = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2, BackColor = Palette.Panel, Padding = new Padding(16, 4, 16, 0) };
        destino.RowStyles.Add(new RowStyle(SizeType.Absolute, 22));
        destino.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        destino.Controls.Add(new Letrero
        {
            Text = "// DESTINO",
            Font = Tipos.Seccion,
            Tracking = 0.2F,
            ForeColor = Palette.Cyan,
            Dock = DockStyle.Fill,
        }, 0, 0);
        var destinoFila = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 3, BackColor = Palette.Panel, Margin = Padding.Empty };
        destinoFila.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 24));
        destinoFila.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        destinoFila.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 128));
        destinoFila.Controls.Add(new Letrero
        {
            Text = ">",
            Font = Tipos.CuerpoGrande,
            ForeColor = Palette.Cyan,
            Dock = DockStyle.Fill,
            Alineacion = ContentAlignment.MiddleCenter,
        }, 0, 0);
        installPath.Dock = DockStyle.Fill;
        installPath.BackColor = Palette.Panel;
        installPath.ForeColor = Palette.Text;
        installPath.BorderStyle = BorderStyle.None;
        installPath.Font = Tipos.CuerpoGrande;
        installPath.Margin = new Padding(0, 8, 12, 4);
        installPath.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "DARK", "app");
        installPath.TextChanged += (_, _) => UpdateStorageSummary();
        destinoFila.Controls.Add(installPath, 1, 0);
        var browse = new Tecla { Text = "Examinar", Estilo = EstiloTecla.Normal, Dock = DockStyle.Fill, Margin = new Padding(0, 3, 0, 3) };
        browse.Click += (_, _) => BrowseDestination();
        destinoFila.Controls.Add(browse, 2, 0);
        destino.Controls.Add(destinoFila, 0, 1);
        content.Controls.Add(destino, 0, 4);

        var condiciones = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 3, BackColor = Palette.Panel, Padding = new Padding(16, 4, 16, 0) };
        condiciones.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        condiciones.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 250));
        condiciones.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        condiciones.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        condiciones.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        condiciones.Controls.Add(new Letrero
        {
            Text = "// CONDICIONES",
            Font = Tipos.Seccion,
            Tracking = 0.2F,
            ForeColor = Palette.Cyan,
            Dock = DockStyle.Fill,
        }, 0, 0);
        thirdPartyNoticesButton.Text = "Ver avisos de terceros";
        thirdPartyNoticesButton.Estilo = EstiloTecla.Texto;
        thirdPartyNoticesButton.Dock = DockStyle.Fill;
        thirdPartyNoticesButton.Margin = new Padding(4, 1, 0, 3);
        thirdPartyNoticesButton.Enabled = HasEmbeddedThirdPartyNotices();
        thirdPartyNoticesButton.Click += (_, _) => ShowThirdPartyNotices();
        condiciones.Controls.Add(thirdPartyNoticesButton, 1, 0);
        terms.Dock = DockStyle.Fill;
        terms.ReadOnly = true;
        terms.Text = TextoLegible(Terms);
        terms.BackColor = Palette.Panel;
        terms.ForeColor = Palette.TextMuted;
        terms.BorderStyle = BorderStyle.None;
        terms.ScrollBars = RichTextBoxScrollBars.None;
        terms.Font = Tipos.Chica;
        terms.Resize += (_, _) => RefrescarScrollTerms();
        var termsHost = new PanelBase { Dock = DockStyle.Fill, BackColor = Palette.Panel, Padding = new Padding(0, 0, 8, 0) };
        termsHost.Controls.Add(terms);
        scrollTerms.Dock = DockStyle.Right;
        termsHost.Controls.Add(scrollTerms);
        condiciones.Controls.Add(termsHost, 0, 1);
        condiciones.SetColumnSpan(termsHost, 2);
        acceptTerms.Texto = "He leído y acepto los términos y condiciones.";
        acceptTerms.Dock = DockStyle.Fill;
        acceptTerms.CheckedChanged += (_, _) => { RefreshControls(); ActualizarGuia(); };
        condiciones.Controls.Add(acceptTerms, 0, 2);
        condiciones.SetColumnSpan(acceptTerms, 2);
        content.Controls.Add(condiciones, 0, 5);

        var progressRow = new PanelTabla { Dock = DockStyle.Fill, ColumnCount = 2, BackColor = Palette.Panel, Padding = new Padding(16, 8, 16, 4) };
        progressRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        progressRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 300));
        progress.Dock = DockStyle.Fill;
        total.Dock = DockStyle.Fill;
        total.Font = Tipos.Micro;
        total.Tracking = 0.03F;
        total.ForeColor = Palette.TextMuted;
        total.Alineacion = ContentAlignment.MiddleRight;
        total.Recortar = true;
        progressRow.Controls.Add(progress, 0, 0);
        progressRow.Controls.Add(total, 1, 0);
        content.Controls.Add(progressRow, 0, 6);

        status.Dock = DockStyle.Fill;
        status.Font = Tipos.Chica;
        status.Tracking = 0.03F;
        status.ForeColor = Palette.Cyan;
        status.Recortar = true;
        status.Padding = new Padding(16, 0, 16, 0);
        content.Controls.Add(status, 0, 7);

        var buttons = new PanelFlujo
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            BackColor = Palette.Panel,
            Padding = new Padding(16, 4, 16, 0),
        };
        installButton.Text = "Descargar archivos";
        installButton.Estilo = EstiloTecla.Primaria;
        installButton.Size = new Size(250, 44);
        installButton.Enabled = false;
        installButton.Click += async (_, _) => await StartInstallAsync();
        cancelButton.Text = "Salir";
        cancelButton.Estilo = EstiloTecla.Texto;
        cancelButton.Size = new Size(190, 44);
        cancelButton.Click += (_, _) => CancelOrClose();
        buttons.Controls.Add(installButton);
        buttons.Controls.Add(cancelButton);
        content.Controls.Add(buttons, 0, 8);
        return content;
    }

    protected override void OnLoad(EventArgs eventArgs)
    {
        base.OnLoad(eventArgs);
        ScrollNativo.ShowScrollBar(artifacts.Handle, ScrollNativo.SB_BOTH, false);
        ScrollNativo.ShowScrollBar(terms.Handle, ScrollNativo.SB_BOTH, false);
        scrollLista.Mover = destino =>
        {
            var info = ScrollNativo.Info(artifacts.Handle, ScrollNativo.SB_VERT);
            var fila = artifacts.Items.Count > 0 ? artifacts.GetItemRect(0).Height : 28;
            SendMessage(artifacts.Handle, ScrollNativo.LVM_SCROLL, IntPtr.Zero,
                (IntPtr)((destino - info.nPos) * fila));
            RefrescarScrollLista();
        };
        scrollTerms.Mover = destino =>
        {
            var punto = new Point(0, destino);
            ScrollNativo.SendMessagePunto(terms.Handle, ScrollNativo.EM_SETSCROLLPOS, IntPtr.Zero, ref punto);
            RefrescarScrollTerms();
        };
        _ = new ScrollHook(artifacts, RefrescarScrollLista);
        _ = new ScrollHook(terms, RefrescarScrollTerms, mensaje =>
        {
            if (mensaje.Msg != ScrollNativo.WM_MOUSEWHEEL) return false;
            var delta = (short)((long)mensaje.WParam >> 16);
            var pos = Point.Empty;
            ScrollNativo.SendMessagePunto(terms.Handle, ScrollNativo.EM_GETSCROLLPOS, IntPtr.Zero, ref pos);
            pos.Y = Math.Max(0, pos.Y - delta / 120 * terms.Font.Height * 3);
            ScrollNativo.SendMessagePunto(terms.Handle, ScrollNativo.EM_SETSCROLLPOS, IntPtr.Zero, ref pos);
            RefrescarScrollTerms();
            return true;
        });
        RefrescarScrollLista();
        RefrescarScrollTerms();
    }

    /// <summary>Quita marcas de markdown para mostrar el texto; el hash firmado sigue siendo el del original.</summary>
    private static string TextoLegible(string markdown)
    {
        var lineas = markdown.ReplaceLineEndings("\n").Split('\n')
            .Select(linea => linea.TrimStart('#', ' ').Replace("**", "").Replace("`", ""));
        return string.Join("\r\n", lineas);
    }

    private void RefrescarScrollLista()
    {
        if (!artifacts.IsHandleCreated) return;
        ScrollNativo.ShowScrollBar(artifacts.Handle, ScrollNativo.SB_BOTH, false);
        var info = ScrollNativo.Info(artifacts.Handle, ScrollNativo.SB_VERT);
        scrollLista.Medir(info.nMax - (int)info.nPage + 1, info.nPos, (int)info.nPage);
    }

    private void RefrescarScrollTerms()
    {
        if (!terms.IsHandleCreated) return;
        var pos = Point.Empty;
        ScrollNativo.SendMessagePunto(terms.Handle, ScrollNativo.EM_GETSCROLLPOS, IntPtr.Zero, ref pos);
        var lineas = (int)SendMessage(terms.Handle, ScrollNativo.EM_GETLINECOUNT, IntPtr.Zero, IntPtr.Zero);
        var max = Math.Max(0, lineas * terms.Font.Height - terms.ClientSize.Height);
        scrollTerms.Medir(max, pos.Y, terms.ClientSize.Height);
    }

    private void DrawArtifactHeader(object? sender, DrawListViewColumnHeaderEventArgs eventArgs)
    {
        using var background = new SolidBrush(Palette.Panel);
        eventArgs.Graphics.FillRectangle(background, eventArgs.Bounds);
        using var underline = new Pen(Color.FromArgb(71, Palette.Cyan), 1F);
        eventArgs.Graphics.DrawLine(underline, eventArgs.Bounds.Left, eventArgs.Bounds.Bottom - 1,
            eventArgs.Bounds.Right, eventArgs.Bounds.Bottom - 1);
        Letrero.DibujarEspaciado(eventArgs.Graphics, eventArgs.Header?.Text ?? "", Tipos.Micro,
            Palette.Cyan, Rectangle.Inflate(eventArgs.Bounds, -8, 0), 0.1F, ContentAlignment.MiddleLeft);
    }

    private static void DrawArtifactRow(object? sender, DrawListViewItemEventArgs eventArgs)
    {
        var color = eventArgs.Item!.Selected ? Palette.Selection
            : eventArgs.ItemIndex % 2 == 0 ? Palette.Panel : Palette.PanelAlternate;
        using var background = new SolidBrush(color);
        eventArgs.Graphics.FillRectangle(background, eventArgs.Bounds);
        using var divider = new Pen(Color.FromArgb(18, Palette.Cyan), 1F);
        eventArgs.Graphics.DrawLine(divider, eventArgs.Bounds.Left, eventArgs.Bounds.Bottom - 1,
            eventArgs.Bounds.Right, eventArgs.Bounds.Bottom - 1);
        if (eventArgs.Item.Selected)
        {
            using var acento = new Pen(Palette.Cyan, 2F);
            eventArgs.Graphics.DrawLine(acento, eventArgs.Bounds.Left + 1, eventArgs.Bounds.Top + 4,
                eventArgs.Bounds.Left + 1, eventArgs.Bounds.Bottom - 5);
        }
    }

    private void DrawArtifactSubItem(object? sender, DrawListViewSubItemEventArgs eventArgs)
    {
        var bounds = Rectangle.Inflate(eventArgs.Bounds, -4, 0);
        if (eventArgs.ColumnIndex == 0)
        {
            var lado = 15;
            var box = new Rectangle(bounds.Left + 4, bounds.Top + (bounds.Height - lado) / 2, lado, lado);
            var artifact = eventArgs.Item?.Tag as ManifestArtifact;
            var isSelected = artifact is not null && selectedArtifactIds.Contains(artifact.Id);
            var figura = Chaflan.Recorte(box.Width, box.Height, 4F);
            using var fill = new SolidBrush(Color.FromArgb(isSelected ? 60 : 31, Palette.Cyan));
            using var outline = new Pen(Color.FromArgb(isSelected ? 210 : 90, Palette.Cyan), 1F);
            var puntos = figura.Select(p => new PointF(box.Left + p.X, box.Top + p.Y)).ToArray();
            eventArgs.Graphics.FillPolygon(fill, puntos);
            eventArgs.Graphics.DrawPolygon(outline, puntos);
            if (isSelected)
            {
                using var check = new Pen(Palette.CyanVivo, 1.8F);
                eventArgs.Graphics.DrawLines(check, [new Point(box.Left + 3, box.Top + 7),
                    new Point(box.Left + 6, box.Top + 11), new Point(box.Left + 12, box.Top + 3)]);
            }
            bounds.X += 28;
            bounds.Width -= 28;
        }
        var fuente = eventArgs.ColumnIndex == 0 ? Tipos.Cuerpo : Tipos.Chica;
        var color = eventArgs.ColumnIndex switch
        {
            0 => eventArgs.Item?.Selected == true ? Palette.Text : Palette.TextBody,
            1 => Palette.TextBody,
            6 => string.Equals(eventArgs.SubItem?.Text, "Opcional", StringComparison.Ordinal) ? Palette.Amber : Palette.TextMuted,
            _ => Palette.TextMuted,
        };
        if (!eventArgs.Item!.Selected && eventArgs.ColumnIndex is 2 or 3 or 4 or 5) color = Palette.TextDim;
        TextRenderer.DrawText(eventArgs.Graphics, eventArgs.SubItem?.Text ?? "", fuente, bounds, color,
            TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
    }

    private void ToggleArtifactAtPointer(object? sender, MouseEventArgs eventArgs)
    {
        var item = artifacts.GetItemAt(eventArgs.X, eventArgs.Y);
        if (item is null || eventArgs.X >= Math.Min(32, artifacts.Columns[0].Width)) return;
        if (item.Tag is not ManifestArtifact artifact || !artifact.Optional) return;
        if (selectedArtifactIds.Contains(artifact.Id))
        {
            if (SelectedArtifacts().Any(selected => selected.Id != artifact.Id
                && DependsOn(selected, artifact.Id, new HashSet<string>(StringComparer.OrdinalIgnoreCase))))
            {
                status.ForeColor = Palette.Amber;
                status.Text = $"> {artifact.DisplayName} es requisito de otro componente seleccionado.";
                return;
            }
            selectedArtifactIds.Remove(artifact.Id);
        }
        else
        {
            IncludeArtifactAndDependencies(artifact);
        }
        acceptTerms.Marcada = false;
        UpdateStorageSummary();
        artifacts.Invalidate(item.Bounds);
    }

    private void IncludeArtifactAndDependencies(ManifestArtifact artifact)
    {
        if (!selectedArtifactIds.Add(artifact.Id)) return;
        foreach (var dependencyId in artifact.DependsOn!)
        {
            var dependency = manifest!.Artifacts.Single(candidate =>
                string.Equals(candidate.Id, dependencyId, StringComparison.OrdinalIgnoreCase));
            IncludeArtifactAndDependencies(dependency);
        }
    }

    private bool DependsOn(ManifestArtifact artifact, string dependencyId, HashSet<string> visited)
    {
        if (!visited.Add(artifact.Id)) return false;
        foreach (var parentDependencyId in artifact.DependsOn!)
        {
            if (string.Equals(parentDependencyId, dependencyId, StringComparison.OrdinalIgnoreCase)) return true;
            var parentDependency = manifest!.Artifacts.Single(candidate =>
                string.Equals(candidate.Id, parentDependencyId, StringComparison.OrdinalIgnoreCase));
            if (DependsOn(parentDependency, dependencyId, visited)) return true;
        }
        return false;
    }

    private void BeginWindowDrag(object? sender, MouseEventArgs eventArgs)
    {
        if (eventArgs.Button != MouseButtons.Left) return;
        ReleaseCapture();
        SendMessage(FindFormHandle(sender), 0xA1, (IntPtr)2, IntPtr.Zero);
    }

    private static IntPtr FindFormHandle(object? sender)
    {
        if (sender is Control control) return control.FindForm()?.Handle ?? IntPtr.Zero;
        return IntPtr.Zero;
    }

    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr handle, int message, IntPtr wParam, IntPtr lParam);

    private void LoadReleaseManifest()
    {
        reviewedLicenseArtifactIds.Clear();
        try
        {
            var publicKey = ReadEmbeddedPublicKey();
            var manifestBytes = ReadReleaseManifestBytes();
            allowedSourceHosts = ReadAllowedSourceHostsLines().Select(line => line.Trim())
                .Where(line => line.Length > 0 && !line.StartsWith('#')).ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (allowedSourceHosts.Count == 0) throw new InvalidDataException("Falta la lista de hosts HTTPS aprobados.");
            manifest = ManifestManager.Verify(manifestBytes, publicKey,
                allowedSourceHosts: allowedSourceHosts);
            if (TermsVersion.Contains("draft", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Las condiciones actuales siguen en borrador y no pueden aceptarse para una instalación de lanzamiento.");
            if (!string.Equals(manifest.Payload.TermsVersion, TermsVersion, StringComparison.Ordinal))
                throw new InvalidDataException("La versión de condiciones no coincide con la versión incluida en el manifiesto firmado.");
            if (!string.Equals(manifest.Payload.TermsSha256, TermsSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("El texto de condiciones no coincide con el SHA-256 firmado en el manifiesto.");
            if (manifest.Artifacts.Count == 0)
                throw new InvalidDataException("El manifiesto verificado no declara componentes descargables.");
            if (manifest.Artifacts.Any(item => item.Kind == "model"))
                throw new InvalidDataException("El manifiesto principal contiene modelos. Los modelos se eligen y descargan después, durante la configuración inicial.");
            var artifactsById = manifest.Artifacts.ToDictionary(item => item.Id, StringComparer.OrdinalIgnoreCase);
            void IncludeWithDependencies(ManifestArtifact artifact)
            {
                if (!selectedArtifactIds.Add(artifact.Id)) return;
                foreach (var dependencyId in artifact.DependsOn!)
                    IncludeWithDependencies(artifactsById[dependencyId]);
            }
            foreach (var required in manifest.Artifacts.Where(item => !item.Optional))
                IncludeWithDependencies(required);
            foreach (var artifact in manifest.Artifacts)
            {
                var row = new ListViewItem(artifact.DisplayName!) { Tag = artifact };
                row.SubItems.Add(artifact.Version);
                row.SubItems.Add(FormatBytes(artifact.SizeBytes));
                row.SubItems.Add(artifact.EstimatedInstalledBytes is { } installed ? FormatBytes(installed) : "Igual a descarga");
                row.SubItems.Add(artifact.Architecture);
                row.SubItems.Add(DescribeAction(artifact.InstallAction));
                row.SubItems.Add(artifact.Optional ? "Opcional" : "Requerido");
                row.SubItems.Add(artifact.Publisher!);
                row.ToolTipText = artifact.Description!;
                artifacts.Items.Add(row);
            }
            if (artifacts.Items.Count > 0) artifacts.Items[0].Selected = true;
            manifestState.ForeColor = Palette.Cyan;
            manifestState.Text = $"Manifiesto verificado · {manifest.Artifacts.Count} componentes · {manifest.PayloadSha256[..12]}…";
            status.ForeColor = Palette.Cyan;
            status.Text = "> Los opcionales empiezan omitidos. Acepta los términos y condiciones para continuar.";
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or CryptographicException
            or InvalidDataException or OverflowException)
        {
            manifest = null;
            manifestState.ForeColor = Palette.Amber;
            manifestState.Text = "> Paquete de lanzamiento incompleto";
            status.ForeColor = Palette.Red;
            status.Text = "> " + error.Message;
            total.Text = "Descarga: no disponible";
        }
        RefreshControls();
        UpdateStorageSummary();
        ActualizarGuia();
    }

    /// <summary>
    /// Dice en la barra de estado cual es el siguiente paso, para que el boton de descarga
    /// nunca parezca bloqueado sin motivo (aceptar terminos y condiciones, revisar espacio...).
    /// </summary>
    private void ActualizarGuia()
    {
        if (manifest is null || working || setupIsRunning) return;
        if (!acceptTerms.Marcada)
        {
            status.ForeColor = Palette.Amber;
            status.Text = "> Paso 1 de 2: lee las condiciones y marca la casilla de confirmación.";
            return;
        }
        if (!installButton.Enabled)
        {
            status.ForeColor = Palette.Amber;
            status.Text = "> No se puede continuar: revisa el espacio libre y la carpeta de destino.";
            return;
        }
        status.ForeColor = Palette.Cyan;
        status.Text = "> Todo listo. Paso 2 de 2: pulsa «Descargar archivos».";
    }

    private void BrowseDestination()
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Elige dónde guardar e instalar D.A.R.K.",
            UseDescriptionForTitle = true,
            SelectedPath = Directory.Exists(installPath.Text) ? installPath.Text : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "DARK"),
        };
        if (dialog.ShowDialog(this) == DialogResult.OK) installPath.Text = dialog.SelectedPath;
    }

    private ManifestArtifact? SelectedArtifact() => artifacts.SelectedItems.Count == 0
        ? null
        : artifacts.SelectedItems[0].Tag as ManifestArtifact;

    private void UpdateSelectedArtifactDetails()
    {
        var artifact = SelectedArtifact();
        selectedDescription.Text = artifact is null
            ? "Selecciona un componente para revisar qué instala, su origen y licencia."
            : $"{artifact.DisplayName} — {artifact.Description} · Editor: {artifact.Publisher} · Licencia: {artifact.LicenseId}";
        detailsTip.SetToolTip(selectedDescription, artifact?.Description ?? "");
        selectedSource.Enabled = selectedLicense.Enabled = artifact is not null;
        // Etiquetas fijas: el host y el id de licencia salen en la descripcion y en el tooltip;
        // como texto del boton eran demasiado largos y se pisaban entre si.
        selectedSource.Text = "Abrir origen";
        selectedLicense.Text = "Abrir licencia";
        detailsTip.SetToolTip(selectedSource, artifact?.SourceUri ?? "");
        detailsTip.SetToolTip(selectedLicense, artifact?.LicenseUri ?? "");
    }

    private void OpenSelectedSource()
    {
        var artifact = SelectedArtifact();
        if (artifact is null) return;
        OpenLink(artifact.SourceUri);
    }

    private static bool HasEmbeddedThirdPartyNotices() =>
        typeof(InstallerForm).Assembly.GetManifestResourceNames().Contains("DarkInstaller.third-party-notices.md");

    private void ShowThirdPartyNotices()
    {
        using var resource = typeof(InstallerForm).Assembly.GetManifestResourceStream("DarkInstaller.third-party-notices.md");
        if (resource is null)
        {
            MessageBox.Show(this, "Este paquete del instalador no trae el índice de avisos de terceros.",
                "Avisos de terceros no disponibles", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        using var reader = new StreamReader(resource, System.Text.Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        using var dialog = new Form
        {
            Text = "D.A.R.K. — Avisos y licencias de terceros",
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.Sizable,
            MinimumSize = new Size(720, 500),
            Size = new Size(980, 720),
            BackColor = Palette.Background,
            ForeColor = Palette.Text,
            Font = Tipos.Cuerpo,
        };
        var layout = new PanelTabla
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            Padding = new Padding(18),
            BackColor = Palette.Background,
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        layout.Controls.Add(new Letrero
        {
            Text = "AVISOS, COMPONENTES Y LICENCIAS INCLUIDOS",
            Font = Tipos.Seccion,
            Tracking = 0.12F,
            ForeColor = Palette.Cyan,
            Dock = DockStyle.Fill,
        }, 0, 0);
        var content = new RichTextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            DetectUrls = true,
            WordWrap = true,
            BorderStyle = BorderStyle.FixedSingle,
            BackColor = Palette.Panel,
            ForeColor = Palette.TextMuted,
            Font = Tipos.Chica,
            Text = reader.ReadToEnd(),
        };
        layout.Controls.Add(content, 0, 1);
        var close = new Tecla
        {
            Text = "Cerrar",
            Estilo = EstiloTecla.Texto,
            Size = new Size(130, 34),
            Anchor = AnchorStyles.Right | AnchorStyles.Bottom,
            Margin = new Padding(0, 6, 0, 0),
        };
        close.Click += (_, _) => dialog.Close();
        layout.Controls.Add(close, 0, 2);
        dialog.Controls.Add(layout);
        dialog.ShowDialog(this);
    }

    private void OpenSelectedLicense()
    {
        var artifact = SelectedArtifact();
        if (artifact is null) return;
        if (!OpenLink(artifact.LicenseUri))
            return;
        reviewedLicenseArtifactIds.Add(artifact.Id);
    }

    private bool OpenLink(string? target)
    {
        if (target is null) return false;
        try
        {
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            return true;
        }
        catch (Exception error)
        {
            MessageBox.Show(this, error.Message, "No se pudo abrir el enlace", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
    }

    private async Task StartInstallAsync()
    {
        if (manifest is null || !acceptTerms.Marcada || working) return;
        var target = installPath.Text.Trim();
        if (string.IsNullOrWhiteSpace(target) || !Path.IsPathFullyQualified(target))
        {
            MessageBox.Show(this, "Elige una carpeta de instalación válida.", "D.A.R.K.", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (!IsSafeInstallTarget(target, out var unsafeTargetReason))
        {
            MessageBox.Show(this, unsafeTargetReason, "Elige otra carpeta", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        target = Path.GetFullPath(target);
        var selected = SelectedArtifacts();
        if (selected.Count == 0)
        {
            MessageBox.Show(this, "Selecciona al menos un componente.", "D.A.R.K.", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        IReadOnlyList<ManifestArtifact> orderedForInstall;
        try { orderedForInstall = OrderSelectedArtifacts(selected); }
        catch (InvalidDataException error)
        {
            MessageBox.Show(this, error.Message, "Falta un componente requerido", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        var downloadRoot = GetDownloadRoot(manifest.PayloadSha256);
        if (!CanFitSelected(selected, target, downloadRoot))
        {
            MessageBox.Show(this, "No se pudo confirmar espacio libre suficiente en el destino y en la carpeta de descargas reanudables.",
                "Espacio insuficiente o no disponible", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            UpdateStorageSummary();
            return;
        }
        if (MessageBox.Show(this,
            $"Se descargarán {selected.Count} componentes ({FormatBytes(selected.Sum(item => item.SizeBytes))}).\nEspacio estimado instalado: {FormatBytes(selected.Sum(item => item.EstimatedInstalledBytes ?? 0))}.\nDestino:\n{target}\n\nLos modelos de IA no están incluidos.",
            "Confirmar instalación", MessageBoxButtons.OKCancel, MessageBoxIcon.Information) != DialogResult.OK) return;

        working = true;
        var runToken = cancellation.BeginRun();
        progress.Valor = 0;
        RefreshControls();
        try
        {
            await SaveTermsAcceptanceAsync(selected, manifest.PayloadSha256, reviewedLicenseArtifactIds);
            Directory.CreateDirectory(downloadRoot);
            using var downloader = new ArtifactDownloader(allowedHosts: allowedSourceHosts);
            var restartPending = false;
            string? installedAppPath = null;
            string? preservedPreviousApp = null;
            var totalBytes = selected.Sum(item => item.SizeBytes);
            long baseBytes = 0;
            foreach (var artifact in orderedForInstall)
            {
                status.ForeColor = Palette.Cyan;
                status.Text = $"> Descargando y verificando {artifact.Id}…";
                var progressReporter = new Progress<DownloadProgress>(item =>
                {
                    if (IsDisposed) return;
                    var done = baseBytes + item.BytesDownloaded;
                    progress.Valor = totalBytes == 0 ? 0 : (int)Math.Clamp(done * 100d / totalBytes, 0, 100);
                });
                await downloader.DownloadAsync(manifest, artifact.Id, downloadRoot, progressReporter, runToken);
                baseBytes += artifact.SizeBytes;
            }
            foreach (var artifact in orderedForInstall)
            {
                runToken.ThrowIfCancellationRequested();
                var packagePath = ResolveContainedPath(downloadRoot, artifact.RelativePath);
                status.Text = $"> {DescribeAction(artifact.InstallAction)}: {artifact.Id}…";
                if (artifact.InstallAction == "extractZip")
                {
                    var extractPath = ResolveContainedPath(target, artifact.InstallTargetPath!);
                    var previous = ExtractAndInstallSafely(packagePath, extractPath, target,
                        artifact.EstimatedInstalledBytes!.Value);
                    if (string.Equals(Path.GetFullPath(extractPath), target, StringComparison.OrdinalIgnoreCase))
                    {
                        installedAppPath = extractPath;
                        preservedPreviousApp = previous;
                    }
                }
                else if (artifact.InstallAction == "runInstaller")
                {
                    using var setupProcess = StartExternalSetup(packagePath);
                    if (setupProcess is null) throw new IOException($"No se pudo iniciar el instalador {artifact.Id}.");
                    try
                    {
                        setupIsRunning = true;
                        status.Text = $"> Completa los pasos de instalación de {artifact.Id}.";
                        RefreshControls();
                        await setupProcess.WaitForExitAsync();
                    }
                    finally
                    {
                        setupIsRunning = false;
                        RefreshControls();
                    }
                    if (!artifact.AllowedExitCodes!.Contains(setupProcess.ExitCode))
                        throw new InvalidOperationException($"El instalador {artifact.Id} terminó con código {setupProcess.ExitCode}.");
                    if (InstallerExitCode.RequiresRestart(setupProcess.ExitCode))
                    {
                        restartPending = true;
                        status.Text = $"> {artifact.Id} se instaló correctamente. Es necesario reiniciar Windows para completar la instalación.";
                        MessageBox.Show(this, status.Text[2..], "Reinicio pendiente", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }
                }
            }
            if (installedAppPath is not null)
            {
                string? uninstallRegistrationWarning = null;
                try
                {
                    var appVersion = orderedForInstall.FirstOrDefault(item => item.InstallAction == "extractZip"
                        && item.InstallTargetPath == ".")?.Version ?? "desconocida";
                    UninstallManager.Register(installedAppPath, appVersion);
                }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException
                                             or InvalidOperationException or System.Security.SecurityException)
                {
                    uninstallRegistrationWarning = "No se pudo registrar la desinstalación por usuario. " + error.Message;
                }
                try { CreateStartMenuShortcut(Path.Combine(installedAppPath, "DarkSupervisor.exe")); }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException or COMException or InvalidOperationException)
                {
                    MessageBox.Show(this, "D.A.R.K. quedó instalado, pero no se pudo crear el acceso del menú Inicio. " + error.Message,
                        "Instalación completada", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
                if (uninstallRegistrationWarning is not null)
                    MessageBox.Show(this, "D.A.R.K. quedó instalado, pero " + uninstallRegistrationWarning,
                        "Desinstalación no registrada", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            status.ForeColor = Palette.Cyan;
            status.Text = restartPending
                ? "> Los componentes se procesaron correctamente. Reinicia Windows para completar la instalación."
                : "> Los componentes configurados se descargaron, verificaron y procesaron.";
            progress.Valor = 100;
            var completionMessage = status.Text[2..];
            if (preservedPreviousApp is not null)
                completionMessage += $"\nLa versión anterior se conservó en:\n{preservedPreviousApp}";
            var noticesPath = installedAppPath is null
                ? null
                : Path.Combine(installedAppPath, "THIRD-PARTY-NOTICES.md");
            MostrarFinal(completionMessage, restartPending, noticesPath, installedAppPath);
        }
        catch (OperationCanceledException)
        {
            status.ForeColor = Palette.Amber;
            status.Text = "> Descarga cancelada. Las descargas parciales se conservan para reanudar.";
        }
        catch (Exception error)
        {
            status.ForeColor = Palette.Red;
            status.Text = $"> No se completó la descarga: {error.Message}";
            MessageBox.Show(this, error.Message, "No se pudo completar", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            working = false;
            cancellation.EndRun();
            RefreshControls();
        }
    }

    private void CancelOrClose()
    {
        if (working) cancellation.Cancel();
        else Close();
    }

    private void RefreshControls()
    {
        var selected = SelectedArtifacts();
        var fits = manifest is not null && selected.Count > 0
            && CanFitSelected(selected, installPath.Text, GetDownloadRoot(manifest.PayloadSha256));
        installButton.Enabled = manifest is not null && acceptTerms.Marcada && !working && fits;
        cancelButton.Text = setupIsRunning ? "Instalación en curso" : working ? "Cancelar descarga" : "Salir";
        cancelButton.Enabled = !setupIsRunning;
        installPath.Enabled = !working;
        acceptTerms.Enabled = manifest is not null && !working;
        progress.Activo = working;
        migas.Estados =
        [
            manifest is not null,
            !string.IsNullOrWhiteSpace(installPath.Text),
            acceptTerms.Marcada,
            working || progress.Valor >= 100,
        ];
        puntoEstado.ForeColor = working ? Palette.Amber : manifest is null ? Palette.Red : Palette.Cyan;
        listaVacia.Visible = artifacts.Items.Count == 0;
        RefrescarScrollLista();
        RefrescarScrollTerms();
        zonaLista.Invalidate();
    }

    private void UpdateStorageSummary()
    {
        if (manifest is null) return;
        var selected = SelectedArtifacts();
        var downloadBytes = selected.Sum(item => item.SizeBytes);
        var installedBytes = selected.Sum(item => item.EstimatedInstalledBytes ?? 0);
        var destinationFree = GetAvailableBytes(installPath.Text);
        var cacheFree = manifest is null ? null : GetAvailableBytes(GetDownloadRoot(manifest.PayloadSha256));
        total.Text = $"Descarga: {FormatBytes(downloadBytes)} · Instalado: {FormatBytes(installedBytes)} · Libre destino: {(destinationFree is { } d ? FormatBytes(d) : "no disponible")} · Libre descargas: {(cacheFree is { } c ? FormatBytes(c) : "no disponible")}";
        var safeTarget = IsSafeInstallTarget(installPath.Text, out var unsafeTargetReason);
        var fits = manifest is not null && CanFitSelected(selected, installPath.Text,
            GetDownloadRoot(manifest.PayloadSha256));
        if (!safeTarget && !working)
        {
            status.ForeColor = Palette.Amber;
            status.Text = "> " + unsafeTargetReason;
        }
        else if (!fits && !working)
        {
            status.ForeColor = Palette.Amber;
            status.Text = "> No se confirmó suficiente espacio libre para el tamaño total de las descargas.";
        }
        else if (status.Text.StartsWith("> No se confirmó suficiente espacio", StringComparison.Ordinal)
                 || status.Text.StartsWith("> Elige una carpeta fuera de las rutas de datos compartidos", StringComparison.Ordinal)
                 || status.Text.StartsWith("> No se puede instalar DARK en la raíz", StringComparison.Ordinal)
                 || status.Text.StartsWith("> La ruta de instalación no es válida:", StringComparison.Ordinal))
        {
            status.ForeColor = Palette.Cyan;
            status.Text = acceptTerms.Marcada
                ? "> Todo listo. Pulsa «Descargar archivos» para iniciar."
                : "> Lee las condiciones y marca la casilla de confirmación para continuar.";
        }
        installButton.Enabled = manifest is not null && acceptTerms.Marcada && !working && fits;
        migas.Estados =
        [
            manifest is not null,
            !string.IsNullOrWhiteSpace(installPath.Text),
            acceptTerms.Marcada,
            working || progress.Valor >= 100,
        ];
    }

    private static long? GetAvailableBytes(string path)
    {
        try
        {
            var fullPath = Path.GetFullPath(path);
            var root = Path.GetPathRoot(fullPath);
            if (string.IsNullOrWhiteSpace(root)) return null;
            return new DriveInfo(root).AvailableFreeSpace;
        }
        catch (Exception error) when (error is ArgumentException or IOException or UnauthorizedAccessException or NotSupportedException)
        {
            return null;
        }
    }

    private static string ReadEmbeddedPublicKey()
    {
        using var stream = typeof(InstallerForm).Assembly.GetManifestResourceStream("DarkInstaller.release-manifest-public.pem")
            ?? throw new FileNotFoundException("Este paquete no incluye la clave pública de confianza para el manifiesto de lanzamiento.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static byte[] ReadReleaseManifestBytes()
    {
        var manifestPath = Path.Combine(AppContext.BaseDirectory, "release-manifest.signed.json");
        if (File.Exists(manifestPath))
            return File.ReadAllBytes(manifestPath);
        using var stream = typeof(InstallerForm).Assembly.GetManifestResourceStream("DarkInstaller.release-manifest.signed.json")
            ?? throw new FileNotFoundException("Este paquete no incluye un manifiesto de lanzamiento firmado.");
        using var buffer = new MemoryStream();
        stream.CopyTo(buffer);
        return buffer.ToArray();
    }

    private static string[] ReadAllowedSourceHostsLines()
    {
        var hostsPath = Path.Combine(AppContext.BaseDirectory, "release-source-hosts.txt");
        if (File.Exists(hostsPath))
            return File.ReadAllLines(hostsPath);
        using var stream = typeof(InstallerForm).Assembly.GetManifestResourceStream("DarkInstaller.release-source-hosts.txt")
            ?? throw new FileNotFoundException("Falta la lista de hosts HTTPS aprobados.");
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        return reader.ReadToEnd().Split(["\r\n", "\n"], StringSplitOptions.None);
    }

    private static byte[] ReadEmbeddedTermsBytes()
    {
        using var stream = typeof(InstallerForm).Assembly.GetManifestResourceStream("DarkInstaller.terms.md")
            ?? throw new FileNotFoundException("Este paquete no incluye el texto de condiciones que se debe mostrar antes de aceptar.");
        using var buffer = new MemoryStream();
        stream.CopyTo(buffer);
        return buffer.ToArray();
    }

    private static string ReadTermsVersion() => ReadAssemblyMetadata("InstallerTermsVersion") ?? "0.1-draft";

    private static string? ReadAssemblyMetadata(string key) => typeof(InstallerForm).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>()
        .SingleOrDefault(attribute => attribute.Key == key)?.Value;

    private static string FormatBytes(long bytes) => bytes >= 1024L * 1024 * 1024
        ? $"{bytes / (1024d * 1024 * 1024):0.00} GB"
        : $"{bytes / (1024d * 1024):0.0} MB";

    private IReadOnlyList<ManifestArtifact> SelectedArtifacts() => artifacts.Items
        .Cast<ListViewItem>()
        .Select(item => (ManifestArtifact)item.Tag!)
        .Where(artifact => selectedArtifactIds.Contains(artifact.Id))
        .ToArray();

    private static IReadOnlyList<ManifestArtifact> OrderSelectedArtifacts(IEnumerable<ManifestArtifact> selected)
    {
        var byId = selected.ToDictionary(artifact => artifact.Id, StringComparer.Ordinal);
        var ordered = new List<ManifestArtifact>(byId.Count);
        var visited = new HashSet<string>(StringComparer.Ordinal);
        void Visit(ManifestArtifact artifact)
        {
            if (!visited.Add(artifact.Id)) return;
            foreach (var dependencyId in artifact.DependsOn!)
            {
                if (!byId.TryGetValue(dependencyId, out var dependency))
                    throw new InvalidDataException($"{artifact.DisplayName} requiere seleccionar también {dependencyId}.");
                Visit(dependency);
            }
            ordered.Add(artifact);
        }
        foreach (var artifact in byId.Values) Visit(artifact);
        return ordered;
    }

    private static long RequiredStorageBytes(IEnumerable<ManifestArtifact> selected) => selected.Sum(artifact =>
        checked(artifact.SizeBytes + (artifact.EstimatedInstalledBytes ?? 0)));

    private static string GetDownloadRoot(string manifestDigest)
    {
        if (manifestDigest.Length != 64 || manifestDigest.Any(character => !Uri.IsHexDigit(character)))
            throw new InvalidDataException("El identificador de descargas del manifiesto no es un SHA-256 válido.");
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "DARK", "setup", "downloads", manifestDigest.ToLowerInvariant());
    }

    private static bool CanFitSelected(IEnumerable<ManifestArtifact> selected, string target, string downloadRoot)
    {
        if (!IsSafeInstallTarget(target, out _)) return false;
        var artifacts = selected.ToArray();
        var downloads = artifacts.Sum(item => item.SizeBytes);
        var installed = artifacts.Sum(item => item.EstimatedInstalledBytes ?? 0);
        var targetFree = GetAvailableBytes(target);
        var downloadsFree = GetAvailableBytes(downloadRoot);
        if (targetFree is null || downloadsFree is null) return false;
        var targetVolume = Path.GetPathRoot(Path.GetFullPath(target));
        var downloadsVolume = Path.GetPathRoot(Path.GetFullPath(downloadRoot));
        return string.Equals(targetVolume, downloadsVolume, StringComparison.OrdinalIgnoreCase)
            ? targetFree >= checked(downloads + installed)
            : targetFree >= installed && downloadsFree >= downloads;
    }

    private static bool IsSafeInstallTarget(string target, out string reason)
    {
        try
        {
            var fullTarget = Path.GetFullPath(target).TrimEnd(Path.DirectorySeparatorChar);
            var volumeRoot = Path.GetPathRoot(Path.GetFullPath(target))?.TrimEnd(Path.DirectorySeparatorChar);
            if (string.IsNullOrWhiteSpace(volumeRoot) || string.Equals(fullTarget, volumeRoot, StringComparison.OrdinalIgnoreCase))
            {
                reason = "No se puede instalar DARK en la raíz de una unidad.";
                return false;
            }

            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var protectedPaths = new[]
            {
                Path.Combine(localAppData, "DARK"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "Temp", "DARK"),
                Path.Combine(Path.GetTempPath(), "DARK"),
            }.Select(path => Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar));
            foreach (var protectedPath in protectedPaths)
            {
                if (PathsOverlap(fullTarget, protectedPath))
                {
                    reason = "Elige una carpeta fuera de las rutas de datos compartidos y temporales de DARK. "
                        + "La aplicación y sus datos deben permanecer separados para que actualizar o desinstalar no borre tus archivos.";
                    return false;
                }
            }

            reason = string.Empty;
            return true;
        }
        catch (Exception error) when (error is ArgumentException or IOException or UnauthorizedAccessException or NotSupportedException)
        {
            reason = "La ruta de instalación no es válida: " + error.Message;
            return false;
        }
    }

    private static bool PathsOverlap(string first, string second) => IsSameOrChildPath(first, second)
        || IsSameOrChildPath(second, first);

    private static bool IsSameOrChildPath(string candidate, string parent)
    {
        candidate = Path.GetFullPath(candidate).TrimEnd(Path.DirectorySeparatorChar);
        parent = Path.GetFullPath(parent).TrimEnd(Path.DirectorySeparatorChar);
        return string.Equals(candidate, parent, StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(parent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Pantalla final: «Abrir D.A.R.K.» lo arranca ya (sin buscarlo en el menú ni usar la terminal) y la casilla deja
    /// D.A.R.K. abriéndose al encender el equipo. Los avisos de terceros siguen a un clic.
    /// </summary>
    private void MostrarFinal(string mensaje, bool reinicioPendiente, string? avisos, string? appPath)
    {
        var supervisor = appPath is null ? null : Path.Combine(appPath, "DarkSupervisor.exe");
        var hayApp = supervisor is not null && File.Exists(supervisor);
        var puedeAbrir = hayApp && !reinicioPendiente;
        var hayAvisos = avisos is not null && File.Exists(avisos);

        var abrir = new TaskDialogButton("Abrir D.A.R.K.");
        var verAvisos = new TaskDialogButton("Ver avisos de terceros") { AllowCloseDialog = false };
        var cerrar = new TaskDialogButton("Cerrar");
        var inicio = new TaskDialogVerificationCheckBox("Abrir D.A.R.K. al encender el equipo", isChecked: true);
        var pagina = new TaskDialogPage
        {
            Caption = reinicioPendiente ? "Reinicio pendiente" : "Instalación completada",
            Heading = reinicioPendiente ? "Falta reiniciar Windows" : "D.A.R.K. está listo",
            Text = mensaje + (hayAvisos ? "\n\nLos avisos y licencias de terceros están en:\n" + avisos : ""),
            Icon = TaskDialogIcon.Information,
            Verification = hayApp ? inicio : null,
            AllowCancel = true,
        };
        if (puedeAbrir) pagina.Buttons.Add(abrir);
        if (hayAvisos) pagina.Buttons.Add(verAvisos);
        pagina.Buttons.Add(cerrar);
        pagina.DefaultButton = puedeAbrir ? abrir : cerrar;
        verAvisos.Click += (_, _) =>
        {
            try { Process.Start(new ProcessStartInfo(avisos!) { UseShellExecute = true }); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException
                                          or System.ComponentModel.Win32Exception)
            {
                MessageBox.Show(this, "No se pudieron abrir los avisos. Puedes consultarlos en:\n" + avisos + "\n\n" + error.Message,
                    "Avisos de terceros", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        };

        var resultado = TaskDialog.ShowDialog(this, pagina);

        if (hayApp)
        {
            try { InicioConWindows.Fijar(supervisor, inicio.Checked); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException
                                          or System.Security.SecurityException)
            {
                MessageBox.Show(this, "No se pudo dejar D.A.R.K. abriéndose al encender el equipo. Puedes activarlo después en "
                    + "el Centro de configuración → Sistema.\n\n" + error.Message,
                    "Inicio con Windows", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
        if (resultado == abrir && supervisor is not null)
        {
            try
            {
                Process.Start(new ProcessStartInfo(supervisor) { UseShellExecute = true, WorkingDirectory = appPath! });
                Close();
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException
                                          or System.ComponentModel.Win32Exception)
            {
                MessageBox.Show(this, "No se pudo abrir D.A.R.K. Ábrelo desde el menú Inicio.\n\n" + error.Message,
                    "Abrir D.A.R.K.", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
    }

    private static void CreateStartMenuShortcut(string executable)
    {
        if (!File.Exists(executable)) throw new FileNotFoundException("No se encontró DarkSupervisor.exe.", executable);
        var programs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs");
        Directory.CreateDirectory(programs);
        var shortcutPath = Path.Combine(programs, "D.A.R.K..lnk");
        var shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new InvalidOperationException("Windows Script Host no está disponible para crear el acceso directo.");
        var shell = Activator.CreateInstance(shellType)
            ?? throw new InvalidOperationException("No se pudo iniciar Windows Script Host.");
        try
        {
            dynamic automation = shell;
            dynamic shortcut = automation.CreateShortcut(shortcutPath);
            shortcut.TargetPath = executable;
            shortcut.WorkingDirectory = Path.GetDirectoryName(executable)!;
            shortcut.Description = "Iniciar D.A.R.K.";
            shortcut.Save();
        }
        finally
        {
            if (Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
        }
    }

    private static string? ExtractAndInstallSafely(string archivePath, string destination, string installRoot,
        long maximumExpandedBytes)
    {
        var fullDestination = Path.GetFullPath(destination);
        var fullRoot = Path.GetFullPath(installRoot);
        var staging = fullDestination + ".installing-" + Guid.NewGuid().ToString("N");
        var backup = fullDestination + ".previous-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss")
            + "-" + Guid.NewGuid().ToString("N");
        var isAppRoot = string.Equals(fullDestination.TrimEnd(Path.DirectorySeparatorChar),
            fullRoot.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase);

        if (File.Exists(fullDestination))
            throw new IOException("La ruta de instalación ya está ocupada por un archivo.");
        if (Directory.Exists(fullDestination) && (File.GetAttributes(fullDestination) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("La carpeta de instalación es un punto de reanálisis.");

        ZipExtractor.ExtractSafely(archivePath, staging, maximumExpandedBytes);
        var extractedRoot = staging;
        if (isAppRoot && (!File.Exists(Path.Combine(extractedRoot, "DarkSupervisor.exe"))
            || !File.Exists(Path.Combine(extractedRoot, "config", "runtime.json"))))
        {
            Directory.Delete(staging, recursive: true);
            throw new InvalidDataException("El ZIP no contiene un layout instalable de D.A.R.K.");
        }

        var hadExistingInstall = Directory.Exists(fullDestination);
        if (hadExistingInstall)
        {
            var existingIsApp = isAppRoot && File.Exists(Path.Combine(fullDestination, "DarkSupervisor.exe"))
                && File.Exists(Path.Combine(fullDestination, "config", "runtime.json"));
            var existingIsEmpty = !Directory.EnumerateFileSystemEntries(fullDestination).Any();
            if (!existingIsApp && !existingIsEmpty)
            {
                Directory.Delete(staging, recursive: true);
                throw new IOException("La carpeta elegida ya contiene archivos ajenos a DARK; no se sobrescribió.");
            }
            if (existingIsApp) EnsureInstalledAppIsStopped(fullDestination);
            if (existingIsEmpty) Directory.Delete(fullDestination);
            else Directory.Move(fullDestination, backup);
        }

        try
        {
            Directory.Move(staging, fullDestination);
        }
        catch
        {
            if (!Directory.Exists(fullDestination) && Directory.Exists(backup))
                Directory.Move(backup, fullDestination);
            if (Directory.Exists(staging)) Directory.Delete(staging, recursive: true);
            throw;
        }
        return Directory.Exists(backup) ? backup : null;
    }

    private static void EnsureInstalledAppIsStopped(string installRoot) =>
        InstalledProcesses.EnsureStopped(installRoot, "actualizar su carpeta de aplicación");

    private static async Task SaveTermsAcceptanceAsync(IReadOnlyList<ManifestArtifact> selected, string manifestSha256,
        IReadOnlySet<string> reviewedLicenseArtifactIds)
    {
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DARK", "setup");
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "terms-acceptance.json");
        var temporary = path + ".tmp";
        var record = new
        {
            schemaVersion = 1,
            termsVersion = TermsVersion,
            termsSha256 = TermsSha256,
            manifestSha256,
            acceptedAtUtc = DateTimeOffset.UtcNow,
            selectedComponents = selected.Select(artifact => new
            {
                artifact.Id, artifact.Version, artifact.LicenseId, artifact.LicenseUri,
                licenseLinkOpened = reviewedLicenseArtifactIds.Contains(artifact.Id),
            }).ToArray(),
            reviewedLicenseComponentIds = selected.Where(artifact => reviewedLicenseArtifactIds.Contains(artifact.Id))
                .Select(artifact => artifact.Id).ToArray(),
        };
        await File.WriteAllTextAsync(temporary, System.Text.Json.JsonSerializer.Serialize(record));
        File.Move(temporary, path, overwrite: true);
    }

    private static string DescribeAction(string action) => action switch
    {
        "extractZip" => "Extraer ZIP",
        "runInstaller" => "Ejecutar instalador",
        _ => "Guardar archivo",
    };

    private static Process? StartExternalSetup(string path) => Process.Start(new ProcessStartInfo(path)
    {
        UseShellExecute = true,
        WorkingDirectory = Path.GetDirectoryName(path)!,
    });

    private static string ResolveContainedPath(string root, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative)
            || relative.Contains(':') || relative.Contains('\0'))
            throw new InvalidDataException("La ruta de instalación no es relativa ni segura.");
        var fullRoot = Path.GetFullPath(root);
        var target = Path.GetFullPath(Path.Combine(fullRoot, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (string.Equals(target, fullRoot, StringComparison.OrdinalIgnoreCase)) return target;
        var prefix = Path.EndsInDirectorySeparator(fullRoot) ? fullRoot : fullRoot + Path.DirectorySeparatorChar;
        if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("La ruta solicitada sale de la carpeta de instalación.");
        return target;
    }

    private static void EnsureNoReparsePath(string root, string target)
    {
        var fullRoot = Path.GetFullPath(root);
        if (Directory.Exists(fullRoot) && (File.GetAttributes(fullRoot) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("La carpeta de destino es un punto de reanálisis.");
        var relativeParent = Path.GetRelativePath(fullRoot, Path.GetDirectoryName(target)!);
        var current = fullRoot;
        foreach (var segment in relativeParent.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            if (Directory.Exists(current) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("La extracción atraviesa un punto de reanálisis.");
        }
        if (File.Exists(target) && (File.GetAttributes(target) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("El archivo destino es un punto de reanálisis.");
    }
}

internal static class Palette
{
    public static readonly Color Background = Color.FromArgb(4, 6, 10);
    public static readonly Color Suelo = Color.FromArgb(1, 2, 5);
    public static readonly Color Panel = Color.FromArgb(5, 8, 15);
    public static readonly Color PanelAlternate = Color.FromArgb(7, 11, 19);
    public static readonly Color Selection = Color.FromArgb(18, 26, 36);
    public static readonly Color Cyan = Color.FromArgb(131, 182, 202);
    public static readonly Color CyanVivo = Color.FromArgb(169, 214, 232);
    public static readonly Color Amber = Color.FromArgb(198, 167, 123);
    public static readonly Color Red = Color.FromArgb(255, 90, 90);
    public static readonly Color Brand = Color.FromArgb(133, 141, 149);
    public static readonly Color Text = Color.FromArgb(232, 241, 248);
    public static readonly Color TextBody = Color.FromArgb(196, 212, 224);
    public static readonly Color TextMuted = Color.FromArgb(150, 170, 185);
    public static readonly Color TextDim = Color.FromArgb(110, 128, 142);
    public static readonly Color TextOff = Color.FromArgb(74, 88, 100);
}

internal static class Tipos
{
    private static readonly string Familia = FuenteMono();
    public static readonly Font Titulo = new(Familia, 20F);
    public static readonly Font Seccion = new(Familia, 9.5F, FontStyle.Bold);
    public static readonly Font Cuerpo = new(Familia, 9.5F);
    public static readonly Font CuerpoGrande = new(Familia, 10.5F);
    public static readonly Font Chica = new(Familia, 8.5F);
    public static readonly Font Micro = new(Familia, 7.5F);
    public static readonly Font Boton = new(Familia, 9F, FontStyle.Bold);
    public static readonly Font Simbolo = new("Segoe UI", 12F);

    private static string FuenteMono()
    {
        using var fuentes = new System.Drawing.Text.InstalledFontCollection();
        var nombres = fuentes.Families.Select(family => family.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (nombres.Contains("Cascadia Mono")) return "Cascadia Mono";
        return nombres.Contains("Consolas") ? "Consolas" : FontFamily.GenericMonospace.Name;
    }
}

internal static class Chaflan
{
    public static PointF[] Puntos(int ancho, int alto, float escala, float? corte = null)
    {
        var lado = Math.Min(ancho, alto);
        var c = corte ?? Math.Min(Math.Max(0.1F * lado, 12F * escala), Math.Min(34F * escala, lado / 2F));
        c = Math.Min(c, lado / 2F);
        return
        [
            new PointF(c, 0), new PointF(ancho - c, 0), new PointF(ancho, c),
            new PointF(ancho, alto - c), new PointF(ancho - c, alto), new PointF(c, alto),
            new PointF(0, alto - c), new PointF(0, c),
        ];
    }

    public static PointF[][] Corchetes(int ancho, int alto, float escala, float? corte = null)
    {
        var figura = Puntos(ancho, alto, escala, corte);
        var c = figura[0].X;
        var largo = Math.Max(0, Math.Min(14F * escala, Math.Min((ancho - 2 * c) / 2, (alto - 2 * c) / 2)));
        var esquinas = new[]
        {
            new[] { figura[6], figura[7], figura[0], figura[1] },
            new[] { figura[0], figura[1], figura[2], figura[3] },
            new[] { figura[2], figura[3], figura[4], figura[5] },
            new[] { figura[4], figura[5], figura[6], figura[7] },
        };
        return esquinas.Select(esquina => new[]
        {
            ALargo(esquina[1], esquina[0], largo), esquina[1], esquina[2], ALargo(esquina[2], esquina[3], largo),
        }).ToArray();
    }

    public static PointF[] Recorte(int ancho, int alto, float corte) =>
    [
        new PointF(0, 0), new PointF(ancho - corte, 0), new PointF(ancho, corte),
        new PointF(ancho, alto), new PointF(0, alto),
    ];

    public static GraphicsPath Ruta(PointF[] puntos)
    {
        var ruta = new GraphicsPath();
        ruta.AddPolygon(puntos);
        return ruta;
    }

    private static PointF ALargo(PointF desde, PointF hacia, float distancia)
    {
        var dx = hacia.X - desde.X;
        var dy = hacia.Y - desde.Y;
        var total = MathF.Sqrt(dx * dx + dy * dy);
        if (total == 0) return desde;
        var k = Math.Min(distancia, total) / total;
        return new PointF(desde.X + dx * k, desde.Y + dy * k);
    }
}

internal sealed class Letrero : Control
{
    private float tracking;

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public float Tracking
    {
        get => tracking;
        set { tracking = value; Invalidate(); }
    }

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public ContentAlignment Alineacion { get; set; } = ContentAlignment.MiddleLeft;
    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public bool Recortar { get; set; }

    public Letrero()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        TabStop = false;
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        if (string.IsNullOrEmpty(Text) || Width <= 0 || Height <= 0) return;
        var interior = new Rectangle(Padding.Left, Padding.Top,
            Math.Max(0, Width - Padding.Horizontal), Math.Max(0, Height - Padding.Vertical));
        DibujarEspaciado(eventArgs.Graphics, Text, Font, ForeColor, interior, Tracking, Alineacion, Recortar);
    }

    public static void DibujarEspaciado(Graphics graphics, string texto, Font fuente, Color color,
        Rectangle bounds, float tracking, ContentAlignment alineacion, bool recortar = false)
    {
        if (bounds.Width <= 0 || bounds.Height <= 0 || texto.Length == 0) return;
        graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
        var avance = TextRenderer.MeasureText(graphics, "M", fuente, new Size(int.MaxValue, int.MaxValue),
            TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix).Width;
        var paso = tracking * fuente.SizeInPoints * graphics.DpiX / 72F;
        var total = avance * texto.Length + paso * (texto.Length - 1);
        var visible = texto.Length;
        var elipsis = false;
        if (recortar && total > bounds.Width)
        {
            visible = Math.Max(0, (int)((bounds.Width - avance) / (avance + paso)));
            elipsis = visible < texto.Length;
        }
        var anchoDibujo = avance * visible + paso * Math.Max(0, visible - 1) + (elipsis ? avance + paso : 0);
        var x = alineacion switch
        {
            ContentAlignment.MiddleCenter or ContentAlignment.TopCenter or ContentAlignment.BottomCenter
                => bounds.Left + (bounds.Width - anchoDibujo) / 2,
            ContentAlignment.MiddleRight or ContentAlignment.TopRight or ContentAlignment.BottomRight
                => bounds.Right - anchoDibujo,
            _ => bounds.Left,
        };
        var flags = TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.VerticalCenter;
        for (var i = 0; i < visible; i++)
        {
            TextRenderer.DrawText(graphics, texto[i].ToString(), fuente,
                new Rectangle((int)Math.Round(x), bounds.Top, avance + 4, bounds.Height), color, flags);
            x += avance + paso;
        }
        if (elipsis)
            TextRenderer.DrawText(graphics, "…", fuente,
                new Rectangle((int)Math.Round(x), bounds.Top, avance + 4, bounds.Height), color, flags);
    }
}

internal sealed class MarcoPanel : Panel
{
    private bool encima;

    public MarcoPanel()
    {
        DoubleBuffered = true;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        BackColor = Palette.Panel;
    }

    private float Escala => DeviceDpi / 96F;

    protected override void OnResize(EventArgs eventArgs)
    {
        base.OnResize(eventArgs);
        if (Width <= 2 || Height <= 2) return;
        using var ruta = Chaflan.Ruta(Chaflan.Puntos(Width, Height, Escala));
        Region = new Region(ruta);
    }

    protected override void OnMouseEnter(EventArgs eventArgs)
    {
        base.OnMouseEnter(eventArgs);
        encima = true;
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs eventArgs)
    {
        base.OnMouseLeave(eventArgs);
        encima = false;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        var bounds = ClientRectangle;
        if (bounds.Width <= 2 || bounds.Height <= 2) return;
        var graphics = eventArgs.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var figura = Chaflan.Puntos(bounds.Width - 1, bounds.Height - 1, Escala);
        using var fill = new SolidBrush(Palette.Panel);
        graphics.FillPolygon(fill, figura);
        using var marco = new Pen(Color.FromArgb(71, Palette.Cyan), 1F) { LineJoin = LineJoin.Miter };
        graphics.DrawPolygon(marco, figura);
        using var corchete = new Pen(Color.FromArgb(encima ? 255 : 230, Palette.Cyan), encima ? 1.5F : 1F)
        { LineJoin = LineJoin.Miter };
        foreach (var esquina in Chaflan.Corchetes(bounds.Width - 1, bounds.Height - 1, Escala))
            graphics.DrawLines(corchete, esquina);
        base.OnPaint(eventArgs);
    }
}

internal sealed class ZonaLista : Panel
{
    public ZonaLista()
    {
        DoubleBuffered = true;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        BackColor = Palette.Panel;
    }

    private float Escala => DeviceDpi / 96F;

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        var graphics = eventArgs.Graphics;
        var largo = 14F * Escala;
        var w = Width - 1;
        var h = Height - 1;
        using var corchete = new Pen(Color.FromArgb(110, Palette.Cyan), 1F);
        graphics.DrawLines(corchete, [new PointF(0, largo), new PointF(0, 0), new PointF(largo, 0)]);
        graphics.DrawLines(corchete, [new PointF(w - largo, 0), new PointF(w, 0), new PointF(w, largo)]);
        graphics.DrawLines(corchete, [new PointF(w, h - largo), new PointF(w, h), new PointF(w - largo, h)]);
        graphics.DrawLines(corchete, [new PointF(largo, h), new PointF(0, h), new PointF(0, h - largo)]);
    }
}

internal static class ScrollNativo
{
    public const int SB_VERT = 1;
    public const int SB_BOTH = 3;
    public const uint SIF_ALL = 0x17;
    public const int WM_MOUSEWHEEL = 0x020A;
    public const int WM_VSCROLL = 0x0115;
    public const int WM_KEYDOWN = 0x0100;
    public const int WM_LBUTTONDOWN = 0x0201;
    public const int LVM_SCROLL = 0x1014;
    public const int EM_GETSCROLLPOS = 0x04DD;
    public const int EM_SETSCROLLPOS = 0x04DE;
    public const int EM_GETLINECOUNT = 0x00BA;

    [StructLayout(LayoutKind.Sequential)]
    public struct SCROLLINFO
    {
        public uint cbSize;
        public uint fMask;
        public int nMin;
        public int nMax;
        public uint nPage;
        public int nPos;
        public int nTrackPos;
    }

    [DllImport("user32.dll")]
    public static extern bool ShowScrollBar(IntPtr handle, int barra, bool mostrar);

    [DllImport("user32.dll")]
    public static extern bool GetScrollInfo(IntPtr handle, int barra, ref SCROLLINFO info);

    [DllImport("user32.dll", EntryPoint = "SendMessage")]
    public static extern IntPtr SendMessagePunto(IntPtr handle, int mensaje, IntPtr wParam, ref Point punto);

    public static SCROLLINFO Info(IntPtr handle, int barra)
    {
        var info = new SCROLLINFO { cbSize = (uint)Marshal.SizeOf<SCROLLINFO>(), fMask = SIF_ALL };
        GetScrollInfo(handle, barra, ref info);
        return info;
    }
}

internal sealed class ScrollHook : NativeWindow
{
    private readonly Control control;
    private readonly Action refrescar;
    private readonly Func<Message, bool>? previo;

    public ScrollHook(Control control, Action refrescar, Func<Message, bool>? previo = null)
    {
        this.control = control;
        this.refrescar = refrescar;
        this.previo = previo;
        if (control.IsHandleCreated) AssignHandle(control.Handle);
        else control.HandleCreated += (_, _) => AssignHandle(control.Handle);
        control.HandleDestroyed += (_, _) => ReleaseHandle();
    }

    protected override void WndProc(ref Message message)
    {
        if (previo?.Invoke(message) == true) return;
        base.WndProc(ref message);
        if (message.Msg is ScrollNativo.WM_MOUSEWHEEL or ScrollNativo.WM_VSCROLL
            or ScrollNativo.WM_KEYDOWN or ScrollNativo.WM_LBUTTONDOWN)
            control.BeginInvoke(refrescar);
    }
}

internal sealed class ScrollLateral : Control
{
    private int maximo;
    private int posicion;
    private int pagina;
    private bool encima;
    private bool arrastrando;
    private int inicioY;
    private int inicioPos;
    private int inicioRecorrido;

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public Action<int>? Mover { get; set; }

    public ScrollLateral()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        Width = 8;
        Cursor = Cursors.Hand;
        TabStop = false;
    }

    public void Medir(int max, int pos, int pag)
    {
        maximo = Math.Max(0, max);
        posicion = Math.Clamp(pos, 0, maximo);
        pagina = Math.Max(1, pag);
        Invalidate();
    }

    private Rectangle Pulgar()
    {
        if (maximo <= 0 || Height <= 0) return Rectangle.Empty;
        var alto = Math.Min(Height, Math.Max(24, (int)((long)Height * pagina / (maximo + pagina))));
        var y = (Height - alto) * posicion / maximo;
        return new Rectangle(1, y, Width - 2, alto);
    }

    protected override void OnMouseEnter(EventArgs eventArgs)
    {
        base.OnMouseEnter(eventArgs);
        encima = true;
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs eventArgs)
    {
        base.OnMouseLeave(eventArgs);
        encima = false;
        Invalidate();
    }

    protected override void OnMouseDown(MouseEventArgs eventArgs)
    {
        base.OnMouseDown(eventArgs);
        var pulgar = Pulgar();
        if (pulgar.Contains(eventArgs.Location))
        {
            arrastrando = true;
            inicioY = eventArgs.Y;
            inicioPos = posicion;
            inicioRecorrido = Height - pulgar.Height;
            Capture = true;
            Invalidate();
        }
        else if (maximo > 0)
        {
            Mover?.Invoke((int)((long)eventArgs.Y * maximo / Math.Max(1, Height)));
        }
    }

    protected override void OnMouseMove(MouseEventArgs eventArgs)
    {
        base.OnMouseMove(eventArgs);
        if (!arrastrando || inicioRecorrido <= 0) return;
        var destino = inicioPos + (eventArgs.Y - inicioY) * maximo / inicioRecorrido;
        Mover?.Invoke(Math.Clamp(destino, 0, maximo));
    }

    protected override void OnMouseUp(MouseEventArgs eventArgs)
    {
        base.OnMouseUp(eventArgs);
        arrastrando = false;
        Capture = false;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        var graphics = eventArgs.Graphics;
        using var track = new SolidBrush(Color.FromArgb(26, Palette.Cyan));
        graphics.FillRectangle(track, 3, 0, 2, Height);
        var pulgar = Pulgar();
        if (pulgar.IsEmpty) return;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var figura = Chaflan.Recorte(pulgar.Width - 1, pulgar.Height - 1, 3F)
            .Select(p => new PointF(pulgar.Left + p.X, pulgar.Top + p.Y)).ToArray();
        using var fill = new SolidBrush(Color.FromArgb(arrastrando || encima ? 140 : 75, Palette.Cyan));
        graphics.FillPolygon(fill, figura);
    }
}

internal enum EstiloTecla
{
    Primaria,
    Normal,
    Texto,
    Simbolo,
}

internal sealed class Tecla : Button
{
    private bool encima;
    private bool presionado;

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public EstiloTecla Estilo { get; set; } = EstiloTecla.Normal;

    public Tecla()
    {
        FlatStyle = FlatStyle.Flat;
        FlatAppearance.BorderSize = 0;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        Cursor = Cursors.Hand;
        Font = Tipos.Boton;
        TabStop = true;
    }

    private float Escala => DeviceDpi / 96F;

    protected override void OnResize(EventArgs eventArgs)
    {
        base.OnResize(eventArgs);
        if (Estilo == EstiloTecla.Texto || Width <= 2 || Height <= 2)
        {
            Region = null;
            return;
        }
        using var ruta = Chaflan.Ruta(Chaflan.Recorte(Width, Height, 10F * Escala));
        Region = new Region(ruta);
    }

    protected override void OnMouseEnter(EventArgs eventArgs)
    {
        base.OnMouseEnter(eventArgs);
        encima = true;
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs eventArgs)
    {
        base.OnMouseLeave(eventArgs);
        encima = false;
        presionado = false;
        Invalidate();
    }

    protected override void OnMouseDown(MouseEventArgs eventArgs)
    {
        base.OnMouseDown(eventArgs);
        presionado = true;
        Invalidate();
    }

    protected override void OnMouseUp(MouseEventArgs eventArgs)
    {
        base.OnMouseUp(eventArgs);
        presionado = false;
        Invalidate();
    }

    protected override void OnEnabledChanged(EventArgs eventArgs)
    {
        base.OnEnabledChanged(eventArgs);
        Invalidate();
    }

    /// <summary>Color opaco del primer ancestro que no sea transparente: es lo que hay "debajo" del botón.</summary>
    private Color FondoDebajo()
    {
        for (var padre = Parent; padre is not null; padre = padre.Parent)
            if (padre.BackColor.A == 255) return padre.BackColor;
        return Palette.Background;
    }

    protected override void OnPaintBackground(PaintEventArgs eventArgs)
    {
        // El botón dibuja con rellenos semitransparentes; sin fondo propio se ven los restos
        // del búfer (texto de otros controles). Se pinta siempre el fondo del padre opaco.
        using var fondo = new SolidBrush(FondoDebajo());
        eventArgs.Graphics.FillRectangle(fondo, ClientRectangle);
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        var graphics = eventArgs.Graphics;
        var bounds = ClientRectangle;
        if (bounds.Width <= 2 || bounds.Height <= 2) return;
        graphics.Clear(FondoDebajo());
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var texto = Estilo == EstiloTecla.Simbolo ? Text : Text.ToUpperInvariant();
        if (Estilo == EstiloTecla.Texto)
        {
            var colorTexto = !Enabled ? Palette.TextOff : encima ? Palette.CyanVivo : Palette.TextMuted;
            Letrero.DibujarEspaciado(graphics, texto, Tipos.Boton, colorTexto, bounds, 0.12F, ContentAlignment.MiddleCenter);
            return;
        }
        var figura = Chaflan.Recorte(bounds.Width - 1, bounds.Height - 1, 10F * Escala);
        int alfa;
        Color color;
        switch (Estilo)
        {
            case EstiloTecla.Primaria:
                alfa = !Enabled ? 14 : presionado ? 96 : encima ? 77 : 46;
                color = Enabled ? Palette.CyanVivo : Palette.TextOff;
                break;
            case EstiloTecla.Simbolo:
                alfa = !Enabled ? 0 : encima ? 50 : 0;
                color = encima ? Palette.Text : Palette.TextMuted;
                break;
            default:
                alfa = !Enabled ? 12 : presionado ? 80 : encima ? 64 : 31;
                color = Enabled ? Palette.TextBody : Palette.TextOff;
                break;
        }
        using var fill = new SolidBrush(Color.FromArgb(alfa, Palette.Cyan));
        graphics.FillPolygon(fill, figura);
        if (Estilo == EstiloTecla.Primaria)
        {
            using var borde = new Pen(Color.FromArgb(Enabled ? encima ? 220 : 150 : 50, Palette.Cyan), 1F);
            graphics.DrawPolygon(borde, figura);
        }
        var fuente = Estilo == EstiloTecla.Simbolo ? Tipos.Simbolo : Tipos.Boton;
        var tracking = Estilo == EstiloTecla.Simbolo ? 0F : 0.12F;
        Letrero.DibujarEspaciado(graphics, texto, fuente, color, bounds, tracking, ContentAlignment.MiddleCenter);
    }
}

internal sealed class Casilla : Control
{
    private bool marcada;
    private bool encima;

    public event EventHandler? CheckedChanged;

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public string Texto { get; set; } = "";

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public bool Marcada
    {
        get => marcada;
        set
        {
            if (marcada == value) return;
            marcada = value;
            CheckedChanged?.Invoke(this, EventArgs.Empty);
            Invalidate();
        }
    }

    public Casilla()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        Cursor = Cursors.Hand;
        TabStop = true;
    }

    private float Escala => DeviceDpi / 96F;

    protected override bool IsInputKey(Keys keyData) =>
        keyData == Keys.Space || base.IsInputKey(keyData);

    protected override void OnKeyDown(KeyEventArgs eventArgs)
    {
        base.OnKeyDown(eventArgs);
        if (eventArgs.KeyCode == Keys.Space && Enabled) Marcada = !Marcada;
    }

    protected override void OnMouseClick(MouseEventArgs eventArgs)
    {
        base.OnMouseClick(eventArgs);
        if (Enabled) Marcada = !Marcada;
    }

    protected override void OnMouseEnter(EventArgs eventArgs)
    {
        base.OnMouseEnter(eventArgs);
        encima = true;
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs eventArgs)
    {
        base.OnMouseLeave(eventArgs);
        encima = false;
        Invalidate();
    }

    protected override void OnEnabledChanged(EventArgs eventArgs)
    {
        base.OnEnabledChanged(eventArgs);
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        var graphics = eventArgs.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var lado = (int)(17 * Escala);
        var box = new Rectangle(0, (Height - lado) / 2, lado, lado);
        var figura = Chaflan.Recorte(box.Width - 1, box.Height - 1, 5F * Escala)
            .Select(p => new PointF(box.Left + p.X, box.Top + p.Y)).ToArray();
        var alfaRelleno = !Enabled ? 10 : marcada ? encima ? 80 : 60 : encima ? 50 : 31;
        using var fill = new SolidBrush(Color.FromArgb(alfaRelleno, Palette.Cyan));
        graphics.FillPolygon(fill, figura);
        using var borde = new Pen(Color.FromArgb(!Enabled ? 50 : marcada ? 220 : 100, Palette.Cyan), 1F);
        graphics.DrawPolygon(borde, figura);
        if (marcada)
        {
            using var check = new Pen(Enabled ? Palette.CyanVivo : Palette.TextOff, 1.8F);
            graphics.DrawLines(check, [
                new PointF(box.Left + lado * 0.2F, box.Top + lado * 0.48F),
                new PointF(box.Left + lado * 0.4F, box.Top + lado * 0.72F),
                new PointF(box.Left + lado * 0.8F, box.Top + lado * 0.2F)]);
        }
        var color = Enabled ? Palette.TextBody : Palette.TextOff;
        var rectTexto = new Rectangle(box.Right + (int)(12 * Escala), 0, Width - box.Right - (int)(12 * Escala), Height);
        Letrero.DibujarEspaciado(graphics, Texto, Tipos.Chica, color, rectTexto, 0.02F, ContentAlignment.MiddleLeft, true);
    }
}

internal sealed class BarraHaz : Control
{
    private int valor;
    private bool activo;
    private float desfase;
    private readonly System.Windows.Forms.Timer reloj = new() { Interval = 33 };

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public int Valor
    {
        get => valor;
        set { valor = Math.Clamp(value, 0, 100); Invalidate(); }
    }

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public bool Activo
    {
        get => activo;
        set
        {
            if (activo == value) return;
            activo = value;
            if (activo) reloj.Start();
            else reloj.Stop();
            Invalidate();
        }
    }

    public BarraHaz()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        TabStop = false;
        reloj.Tick += (_, _) =>
        {
            desfase += 1F;
            Invalidate();
        };
    }

    private float Escala => DeviceDpi / 96F;

    protected override void Dispose(bool disposing)
    {
        if (disposing) reloj.Dispose();
        base.Dispose(disposing);
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        var bounds = ClientRectangle;
        if (bounds.Width <= 4 || bounds.Height <= 4) return;
        var graphics = eventArgs.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var figura = Chaflan.Puntos(bounds.Width - 1, bounds.Height - 1, Escala,
            Math.Min(10F * Escala, (bounds.Height - 1) / 3F));
        using var fill = new SolidBrush(Palette.Panel);
        graphics.FillPolygon(fill, figura);

        var corte = figura[0].X;
        var inset = corte / 2 + 3;
        var pista = new RectangleF(inset, inset, bounds.Width - 1 - inset * 2, bounds.Height - 1 - inset * 2);
        if (pista.Width > 0 && pista.Height > 0 && valor > 0)
        {
            var lleno = new RectangleF(pista.X, pista.Y, pista.Width * valor / 100F, pista.Height);
            using var relleno = new SolidBrush(Color.FromArgb(90, Palette.Cyan));
            graphics.FillRectangle(relleno, lleno);
            if (valor < 100)
            {
                using var frente = new Pen(Color.FromArgb(220, Palette.CyanVivo), 1.5F);
                graphics.DrawLine(frente, lleno.Right, lleno.Top, lleno.Right, lleno.Bottom);
            }
        }

        using var marco = new Pen(Color.FromArgb(71, Palette.Cyan), 1F) { LineJoin = LineJoin.Miter };
        graphics.DrawPolygon(marco, figura);
        var encendido = activo || valor >= 100;
        using var corchete = new Pen(Color.FromArgb(encendido ? 255 : 230, Palette.Cyan), encendido ? 1.5F : 1F)
        { LineJoin = LineJoin.Miter };
        foreach (var esquina in Chaflan.Corchetes(bounds.Width - 1, bounds.Height - 1, Escala,
            Math.Min(10F * Escala, (bounds.Height - 1) / 3F)))
            graphics.DrawLines(corchete, esquina);

        Letrero.DibujarEspaciado(graphics, $"{valor} %", Tipos.Micro, Palette.TextMuted,
            Rectangle.Inflate(bounds, -(int)inset - 6, 0), 0.08F, ContentAlignment.MiddleRight);

        if (!activo) return;
        var perimetro = 0F;
        for (var i = 0; i < figura.Length; i++)
        {
            var siguiente = figura[(i + 1) % figura.Length];
            perimetro += MathF.Sqrt(MathF.Pow(siguiente.X - figura[i].X, 2) + MathF.Pow(siguiente.Y - figura[i].Y, 2));
        }
        const float grosor = 1.5F;
        using var haz = new Pen(Color.FromArgb(230, Palette.CyanVivo), grosor)
        {
            LineJoin = LineJoin.Miter,
            DashPattern = [perimetro * 0.14F / grosor, perimetro * 0.86F / grosor],
            DashOffset = -(desfase % 48F) / 48F * perimetro / grosor,
        };
        graphics.DrawPolygon(haz, figura);
    }
}

internal sealed class Migas : Control
{
    private static readonly string[] Pasos = ["COMPONENTES", "DESTINO", "CONDICIONES", "DESCARGA"];
    private bool[] estados = [false, false, false, false];

    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public bool[] Estados
    {
        get => estados;
        set { estados = value; Invalidate(); }
    }

    public Migas()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
            | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        TabStop = false;
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        if (Width <= 0 || Height <= 0) return;
        var graphics = eventArgs.Graphics;
        graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
        var fuente = Font;
        var avance = TextRenderer.MeasureText(graphics, "M", fuente, new Size(int.MaxValue, int.MaxValue),
            TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix).Width;
        var paso = 0.14F * fuente.SizeInPoints * graphics.DpiX / 72F;
        const string separador = "  →  ";
        // Cada caracter (incluidos los de los separadores) avanza avance + paso al dibujarse.
        var totalCaracteres = Pasos.Sum(p => p.Length) + (Pasos.Length - 1) * separador.Length;
        var total = totalCaracteres * (avance + paso) - paso;
        var x = Width - total;
        var actual = Array.IndexOf(estados, false);
        var flags = TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.VerticalCenter;
        for (var i = 0; i < Pasos.Length; i++)
        {
            var color = estados[i] ? Palette.Cyan : i == actual ? Palette.TextBody : Palette.TextOff;
            foreach (var caracter in Pasos[i])
            {
                TextRenderer.DrawText(graphics, caracter.ToString(), fuente,
                    new Rectangle((int)Math.Round(x), 0, avance + 4, Height), color, flags);
                x += avance + paso;
            }
            if (i == Pasos.Length - 1) continue;
            foreach (var caracter in separador)
            {
                TextRenderer.DrawText(graphics, caracter.ToString(), fuente,
                    new Rectangle((int)Math.Round(x), 0, avance + 4, Height), Palette.TextOff, flags);
                x += avance + paso;
            }
        }
    }
}

internal sealed class TesseractGlyph : Control
{
    [System.ComponentModel.Browsable(false)]
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public float Opacidad { get; set; } = 1F;

    public TesseractGlyph()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        TabStop = false;
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        var graphics = eventArgs.Graphics;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var width = ClientSize.Width;
        var height = ClientSize.Height;
        if (width < 16 || height < 16) return;
        var size = Math.Min(width, height) * 0.72F;
        var center = new PointF(width / 2F, height / 2F);
        PointF Project(int cube, int vertex)
        {
            var x = (vertex & 1) == 0 ? -1F : 1F;
            var y = (vertex & 2) == 0 ? -1F : 1F;
            var z = (vertex & 4) == 0 ? -1F : 1F;
            var offset = cube == 0 ? -0.19F : 0.19F;
            return new PointF(center.X + size * (x * 0.27F + z * 0.12F + offset),
                center.Y + size * (y * 0.27F - z * 0.12F - offset * 0.45F));
        }

        foreach (var alpha in new[] { 24, 65 })
        {
            using var halo = new Pen(Color.FromArgb((int)(alpha * Opacidad), Palette.Cyan), alpha == 24 ? 7F : 3F) { LineJoin = LineJoin.Round };
            DrawWireframe(graphics, halo, Project);
        }
        using var crisp = new Pen(Color.FromArgb((int)(220 * Opacidad), Palette.Cyan), 1.25F) { LineJoin = LineJoin.Round };
        DrawWireframe(graphics, crisp, Project);
        using var nodeBrush = new SolidBrush(Color.FromArgb((int)(220 * Opacidad), Palette.Text));
        for (var cube = 0; cube < 2; cube++)
            for (var vertex = 0; vertex < 8; vertex++)
            {
                var point = Project(cube, vertex);
                graphics.FillEllipse(nodeBrush, point.X - 1.5F, point.Y - 1.5F, 3F, 3F);
            }
    }

    private static void DrawWireframe(Graphics graphics, Pen pen, Func<int, int, PointF> project)
    {
        for (var cube = 0; cube < 2; cube++)
            for (var vertex = 0; vertex < 8; vertex++)
                for (var bit = 0; bit < 3; bit++)
                {
                    var other = vertex ^ (1 << bit);
                    if (other <= vertex) continue;
                    graphics.DrawLine(pen, project(cube, vertex), project(cube, other));
                }
        for (var vertex = 0; vertex < 8; vertex++)
            graphics.DrawLine(pen, project(0, vertex), project(1, vertex));
    }
}

/// <summary>Panel con doble búfer: sin esto los hijos transparentes dejan restos al recolocarse.</summary>
internal sealed class PanelBase : Panel
{
    public PanelBase()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        DoubleBuffered = true;
    }
}

internal sealed class PanelTabla : TableLayoutPanel
{
    public PanelTabla()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        DoubleBuffered = true;
    }
}

internal sealed class PanelFlujo : FlowLayoutPanel
{
    public PanelFlujo()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        DoubleBuffered = true;
    }
}
