import React from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  NavLink,
  useLocation
} from 'react-router-dom';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Container from '@mui/material/Container';
import Box from '@mui/material/Box';
import Fab from '@mui/material/Fab';
import Zoom from '@mui/material/Zoom';
import CircularProgress from '@mui/material/CircularProgress';
import Tooltip from '@mui/material/Tooltip';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';

import AnalysisPage from './pages/Analysis';
import PortfolioPage from './pages/Portfolio';
import YieldCurvePage from './pages/YieldCurve';
import TopStocksByGroupPage from './pages/TopStocksByGroup';
import PromptConfigPage from './pages/PromptConfig';
import { StockSelectionTaskProvider, useStockSelectionTask } from './context/StockSelectionTaskContext';
import { RiskFreeRateTaskProvider } from './context/RiskFreeRateTaskContext';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
  },
});

const Navigation = () => {
  const location = useLocation();
  const { recomputeLoading } = useStockSelectionTask();

  const getButtonStyle = (path) => {
    const isActive = location.pathname === path;
    return {
      color: 'white',
      borderBottom: isActive ? '2px solid white' : '2px solid transparent',
      borderRadius: 0,
      '&:hover': {
        borderBottom: '2px solid rgba(255,255,255,0.7)',
      }
    };
  };

  return (
    <AppBar position="static" elevation={2}>
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
          Trader Intelligence
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <Button component={NavLink} to="/" sx={getButtonStyle('/')}>
            Analysis
          </Button>
          <Button component={NavLink} to="/portfolio" sx={getButtonStyle('/portfolio')}>
            Portfolio
          </Button>
          <Button component={NavLink} to="/rates" sx={getButtonStyle('/rates')}>
            Rates
          </Button>
          <Button component={NavLink} to="/stock-selection" sx={getButtonStyle('/stock-selection')}>
            <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
              Stock Selection
              {recomputeLoading && (
                <Tooltip title="Snapshot recomputation running in the background">
                  <CircularProgress size={14} color="inherit" aria-label="Stock selection recomputing" />
                </Tooltip>
              )}
            </Box>
          </Button>
          <Button component={NavLink} to="/config" sx={getButtonStyle('/config')}>
            Config
          </Button>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

const ScrollToTopButton = () => {
  const [showButton, setShowButton] = React.useState(false);

  React.useEffect(() => {
    const handleScroll = () => {
      setShowButton(window.scrollY > 300);
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll();

    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const handleScrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: 'smooth',
    });
  };

  return (
    <Zoom in={showButton}>
      <Fab
        color="primary"
        size="medium"
        aria-label="scroll back to top"
        onClick={handleScrollToTop}
        sx={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: (theme) => theme.zIndex.tooltip + 1,
        }}
      >
        <KeyboardArrowUpIcon />
      </Fab>
    </Zoom>
  );
};

const App = () => {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <StockSelectionTaskProvider>
          <RiskFreeRateTaskProvider>
            <Navigation />
            <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
              <Routes>
                <Route path="/" element={<AnalysisPage />} />
                <Route path="/portfolio" element={<PortfolioPage />} />
                <Route path="/rates" element={<YieldCurvePage />} />
                <Route path="/stock-selection" element={<TopStocksByGroupPage />} />
                <Route path="/config" element={<PromptConfigPage />} />
              </Routes>
            </Container>
            <ScrollToTopButton />
          </RiskFreeRateTaskProvider>
        </StockSelectionTaskProvider>
      </Router>
    </ThemeProvider>
  );
};

export default App;
